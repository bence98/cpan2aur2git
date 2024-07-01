#!/usr/bin/python
import argparse
import os
import re
import requests
import subprocess
import signal
import sys
import time

from dataclasses import dataclass
from os.path import isfile
from typing import List

@dataclass
class ArchPackage:
    name: str
    perlname: str
    required_version: str

    version: str

    provided_by: str
    provided_version: str

    repo: str
    maintainer: str
    depends: list

    cached: bool = False


def main():
    #if len(sys.argv) != 2:
    #    print_usage_and_exit()

    cli_parser = argparse.ArgumentParser(
            usage="""%(prog)s <COMMAND> <KOHADIR>
commands:
   PKGBUILD|p       print the PKGBUILD for the koha-perldeps AUR-package.
   deptree|d        print the AUR dependency-tree
   help|h           print the help
            """,
            description="Script helps with perl-dependencies of Koha for ArchLinux.",
            epilog="""
It takes the koha-directory of the unpacked release-tarball,
which can be found under https://download.koha-community.org
and prints the PKGBUILD or generates the AUR dependency-tree
of the koha perl-dependencies meta-package
for the AUR (ArchLinux User Repositories).

    """)
    cli_parser.add_argument("command", metavar="COMMAND", help="<PKGBUILD|deptree|help>")
    cli_parser.add_argument("kohadir", metavar="KOHADIR", help="the koha-directory")
    args = cli_parser.parse_args()


    command = "help"
    if args.command in ["PKGBUILD", "p"]:
        command = "PKGBUILD"
    elif args.command in ["deptree", "d"]:
        command = "deptree"

    if command == "help":
        cli_parser.print_usage()
        sys.exit(1)

    kohadir = args.kohadir.rstrip("/")
    kohaversion = get_koha_version(kohadir)
    if not kohaversion:
        sys.exit(2)

    archpkgs_cache = load_cache(kohadir + ".cache")
    koha_perldeps = get_koha_perldeps(kohadir)
    if not koha_perldeps:
        sys.exit(3)

    # I don't want a stacktrace on CTRL+C.
    def sigint_handler(sig, frame):
        save_cache(kohadir + ".cache", archpkgs_cache)
        sys.exit(0)
    signal.signal(signal.SIGINT, sigint_handler)

    # Build up cache.
    printed_tick = False
    for perlname, installed_version, required_version in koha_perldeps:
        archpkg = request_archpkg(perlname, required_version, archpkgs_cache)
        if not archpkg:
            archpkgname = perlname2archpkgname(perlname)
            if printed_tick:
                print("") # print newline
                printed_tick = False
            print("Warning: Didn't find {0} neighter in the ArchLinux Package-Repos nor the AUR!".format(archpkgname),
                  file = sys.stderr)
            continue
        if not archpkg.cached:
            archpkgs_cache.append(archpkg)
            print(".", end='', flush=True)
            printed_tick = True
            time.sleep(0.5) # Don't spam the servers with requests.

    save_cache(kohadir + ".cache", archpkgs_cache)

    if printed_tick:
        print("") # print newline

    # ---

    if command == "PKGBUILD":
        perlversion = check_current_perlversion(koha_perldeps, archpkgs_cache)
        printPKGBUILD(kohaversion, perlversion, koha_perldeps, archpkgs_cache)

    elif command == "deptree":

        # Build up extended cache.
        printed_tick = False
        for archpkg in filter(lambda archpkg: archpkg.repo == "aur", archpkgs_cache):

            deps = list(filter(lambda name: name.startswith("perl-"), archpkg.depends))

            for dep in deps:
                (archpkgname, required_version) = dep.split(">=") if len(dep.split(">=")) == 2 else [dep, ""]
                perlname = archpkgname2perlname(archpkgname)
                archpkg = request_archpkg(perlname, required_version, archpkgs_cache)
                if not archpkg:
                    if printed_tick:
                        print("") # print newline
                        printed_tick = False
                    print("Warning: Didn't find {0} neighter in the ArchLinux Package-Repos nor the AUR!".format(archpkgname),
                          file = sys.stderr)
                    continue

                if not archpkg.cached:
                    archpkgs_cache.append(archpkg)
                    print(".", end='', flush=True)
                    printed_tick = True
                    time.sleep(0.5) # Don't spam the servers with requests.
                    save_cache(kohadir + ".cache", archpkgs_cache)

                if not archpkg.repo == "aur":
                    continue

                for dep in archpkg.depends:
                    if not dep.startswith("perl-"):
                        continue
                    if not dep in deps:
                        deps.append(dep)

        if printed_tick:
            print("") # print newline
            printed_tick = False
        printAURdeptree(koha_perldeps, archpkgs_cache)

# ---

perlname_provided_by_dict = {
    "CGI::Carp"                     : "perl-cgi",
    "CPAN::Meta"                    : "perl",
    "Crypt::Eksblowfish::Bcrypt"    : "perl-crypt-eksblowfish",
    "Data::Dumper"                  : "perl",
    "Digest::MD5"                   : "perl",
    "Digest::SHA"                   : "perl",
    "GD::Barcode::UPCE"             : "perl-gd-barcode",
    "Getopt::Long"                  : "perl",
    "Getopt::Std"                   : "perl",
    "HTML::Entities"                : "perl-html-parser",
    "HTML::FormatText"              : "perl-html-formatter",
    "HTTP::Request::Common"         : "perl-http-message",
    "HTTP::Tiny"                    : "perl",
    "IPC::Cmd"                      : "perl",
    "List::Util"                    : "perl",
    "Locale::Messages"              : "perl-libintl-perl",
    "LWP::Simple"                   : "perl-libwww",
    "LWP::UserAgent"                : "perl-libwww",
    "MARC::Record::MiJ"             : "perl-marc-file-mij",
    "MIME::Base64"                  : "perl",
    "POSIX"                         : "perl",
    "Storable"                      : "perl",
    "Template"                      : "perl-template-toolkit",
    "Term::ANSIColor"               : "perl",
    "Test"                          : "perl",
    "Test::More"                    : "perl",
    "Text::Balanced"                : "perl",
    "Text::Wrap"                    : "perl",
    "Time::HiRes"                   : "perl",
    "Time::localtime"               : "perl",
    "Unicode::Normalize"            : "perl",
    "URI::Escape"                   : "perl-uri",
    "XML::SAX::ParserFactory"       : "perl-xml-sax",
    "YAML::XS"                      : "perl-yaml-libyaml",
}


def request_archpkg(perlname: str, required_version: str, archpkgs_cache: List[ArchPackage]):
    archpkg = list(filter(lambda archpkg: archpkg.perlname == perlname, archpkgs_cache))
    archpkg = archpkg[0] if archpkg != [] else None
    if archpkg:
        return archpkg

    archpkgname = perlname2archpkgname(perlname)
    provided_by = perlname_provided_by_dict[perlname] if perlname in perlname_provided_by_dict else archpkgname

    archpkg = request_archpkg_info(archpkgname, provided_by)
    if not archpkg:
        archpkg = request_aurpkg_info(archpkgname, provided_by)

    if not archpkg:
        return None

    archpkg.perlname = perlname
    archpkg.required_version = required_version
    return archpkg


def request_archpkg_info(archpkgname, provided_by):
    resp = requests.get("https://archlinux.org/packages/search/json/?name=" + provided_by,
                 headers = { 'User-Agent': 'KohaAURBot/1.0 '+requests.utils.default_user_agent() })
    resp.raise_for_status()
    data = resp.json()

    if len(data["results"]) < 1:
        # raise KeyError("No package named '{0}' found in Arch-repos!".format("perl-yaml-libyaml"))
        return None

    data = data["results"]

    #archpkgname = data[0]["pkgname"]
    pkgver      = data[0]["pkgver"]
    repo        = data[0]["repo"]
    maintainer  = data[0]["maintainers"][0] if len(data[0]["maintainers"]) > 0 else ""
    depends     = data[0]["depends"]

    name_ver = list(filter(lambda name_ver: name_ver.split("=")[0] == archpkgname, data[0]["provides"]))
    assert 0 <= len(name_ver) <= 1
    name_ver = name_ver[0].split("=") if name_ver else []
    assert 0 <= len(name_ver) <= 2, "Something wrong with provides for " + archpkgname
    version = name_ver[1] if len(name_ver) == 2 else pkgver

    depends = list(map(lambda dep: dep.removesuffix(">=0"), depends))

    #ArchPackage(name, perlname, required_version, version, provided_by, provided_version, repo, maintainer, depends)
    return ArchPackage(archpkgname, "", "", version, provided_by, pkgver, repo, maintainer, depends)


def request_aurpkg_info(aurpkgname, provided_by):
    resp = requests.get("https://aur.archlinux.org/rpc/v5/info?arg%5B%5D=" + provided_by,
                 headers = { 'User-Agent': 'KohaAURBot/1.0 '+requests.utils.default_user_agent() })
    resp.raise_for_status()
    data = resp.json()

    if len(data["results"]) < 1:
        # raise KeyError("No package named '{0}' found in Arch-repos!".format("perl-yaml-libyaml"))
        return None

    data = data["results"]

    #aurpkgname = data[0]["Name"]
    pkgver      = data[0]["Version"]
    repo        = "aur"
    maintainer  = data[0]["Maintainer"]
    depends     = data[0]["Depends"] if "Depends" in data[0] else []

    pkgver = pkgver.split("-", 1)[0]
    pkgver = pkgver.split("_", 1)[0] # Remove pkgrel from version (everything after "-" or "_").

    version = pkgver
    if "Provides" in data[0]:
        name_ver = list(filter(lambda name_ver: name_ver.split("=")[0] == aurpkgname, data[0]["Provides"]))
        assert 0 <= len(name_ver) <= 1
        name_ver = name_ver[0].split("=") if name_ver else []
        assert 0 <= len(name_ver) <= 2, "Something wrong with provides for " + archpkgname
        version = name_ver[1] if len(name_ver) == 2 else pkgver

    depends = list(map(lambda dep: dep.removesuffix(">=0"), depends))

    #ArchPackage(name, perlname, required_version, version, provided_by, provided_version, repo, maintainer, depends)
    return ArchPackage(aurpkgname, "", "", version, provided_by, pkgver, repo, maintainer, depends)


def get_koha_perldeps(kohadir: str):
    """Extracts the Koha perl-dependency from the output of kohadir/misc/devel/koha_perl_deps.pl."""

    kohaperldeps_pl = kohadir + "/misc/devel/koha_perl_deps.pl"

    env = os.environ.copy()
    env["PERL5LIB"] = kohadir
    complete_proc = subprocess.run(
            ["perl", kohaperldeps_pl, "--all", "--required"],
            env = env, check=True, stdout = subprocess.PIPE)

    if not isfile(kohaperldeps_pl):
        print("Error: File `{0}' doesn't exist!".format(kohaperldeps_pl), file = sys.stderr)
        return None

    perldeps = []
    started = False
    version_pattern = r"(0 \*|v?\d+|v?\d+\.\d+|v?\d+\.\d+\.\d+|\d+\.\d+_\d+)";
    pattern = re.compile(r"^([\w:]+)\s+" + version_pattern + r"\s+" + version_pattern + r"\s+Yes$")
    for line in complete_proc.stdout.decode("utf-8").splitlines():
        if not started and not re.match("^-+$", line):
            continue
        elif not started and re.match("^-+$", line):# Header-line "-----..." encountered, now the modules start.
            started = True
            continue
        elif started and re.match("^$", line):      # skip empty lines
            continue
        elif started and re.match("^-+$", line):    # Footer-line "-----..." encountered, we are finished.
            break
        else:
            result = pattern.match(line)
            if not result:
                print("Warning: Strange line encountered `" + line + "'.", file = sys.stderr)
            else:
                perlname = result.group(1)

                installed_version = result.group(2)
                required_version = result.group(3)
                required_version = required_version.removeprefix("v");

                perldeps.append((perlname, installed_version, required_version))

    return perldeps

# ---

def perlname2archpkgname(perlname: str):
    """Converts the Perl CPAN module-name to the corresponding ArchLinux package-name."""
    return "perl-" + perlname.lower().replace("::", "-").replace("_", "-")


def archpkgname2perlname(archpkgname: str):
    """Converts the ArchLinux package-name to the corresponding Perl CPAN module-name."""

    toupper_parts = ["cgi", "csv", "dbi", "gd", "md5", "html", "http", "ipc", "json", "lwp", "marc",
        "mime", "pdf", "posix", "psgi", "sax", "sha", "ssl", "tcp", "ttf", "upce", "uri", "yaml", "www"];
    touppers = ["sql", "xml", "xslt"] # for LibXML, LibXSLT, RunSQL
    archpart2perlpart_dict = {
        "ansicolor"     : "ANSIColor",
        "datetime"      : "DateTime",
        "formattext"    : "FormatText",
        "hires"         : "HiRes",
        "ical"          : "ICal",
        "parserfactory" : "ParserFactory",
        "sharedir"      : "ShareDir",
        "sharedfork"    : "SharedFork",
        "timezone"      : "TimeZone",
        "useragent"     : "UserAgent",
        "urlencoded"    : "UrlEncoded"}

    archpkgname = archpkgname.removeprefix("perl-");
    archparts = archpkgname.split("-")
    perlparts = []

    for archpart in archparts:
        perlpart = ""
        if archpart in toupper_parts:
            perlpart = archpart.upper()
        elif archpart in archpart2perlpart_dict:
            perlpart = archpart2perlpart_dict[archpart]
        else:
            perlpart = archpart.title()
            for toupper in touppers:
                perlpart = perlpart.replace(toupper, toupper.upper())
                perlpart = perlpart.replace(toupper.title(), toupper.upper())

        assert perlpart
        perlparts.append(perlpart)

    return "::".join(perlparts)

# ---

def get_koha_version(kohadir : str):
    """Extract the Koha-version from Koha.pm in kohadir."""
    if not isfile(kohadir + "/Koha.pm"):
        print("Error: File `{0}' doesn't exist!".format(kohadir + "/Koha.pm"), file = sys.stderr)
        return None

    version = grep(r"\$VERSION = \"(\d+\.\d+\.\d+)\.\d+\";", kohadir + "/Koha.pm")
    if not version:
        print("Error: Can't find Koha-version in Koha.pm!", file = sys.stderr)
        return None

    return version[0].group(1)


def grep(patternstr : str, filename : str):
    """
    Match patternstr to each line of filename.
    Returns:
        A list of Match objects (as returned by re.match()) for every line that matches
    """
    results = []
    pattern = re.compile(patternstr)
    try:
        file = open(filename, "r")
    except Exception as e:
        print("Error: Can't open `{0}' for reading:".format(filename), e, file = sys.stderr)
    else:
        with file:
            for line in file:
                result = pattern.match(line)
                if result:
                    results.append(result)
    return results

#---

# Note: provides in the perl-ArchPackage doesn't list all the packages provided by it,
#       see https://archlinux.org/packages/search/json/?name=perl.
#       E.g. perl-time-localtime, perl-getopt-std, perl-posix, ...
def check_current_perlversion(perldeps: list, archpkgs_cache: List[ArchPackage]):

    resp = requests.get("https://archlinux.org/packages/search/json/?name=perl",
                 headers = { 'User-Agent': 'KohaAURBot/1.0 '+requests.utils.default_user_agent() })
    resp.raise_for_status()
    data = resp.json()
    assert len(data["results"]) == 1
    perlversion = data["results"][0]["pkgver"]

    for perlname, installed_version, required_version in perldeps:
        archpkg = list(filter(lambda archpkg: archpkg.perlname == perlname, archpkgs_cache))
        assert len(archpkg) >= 1, "No ArchLinux-packages found for " + perlname + " in cache!?"
        assert len(archpkg) == 1, "Multiple ArchLinux-packages found for " + perlname + " in cache!?"
        archpkg = archpkg[0]

        # Here we are only interested in the perl-modules that a provided by the perl-ArchPackage.
        # Skip the others.
        if archpkg.provided_by != "perl":
            continue

        if installed_version < required_version:
            print(("Error: perl module `{0}' provided by the perl ArchLinux-Package is too old: {1} < {2}!")\
                    .format(perlname, installed_version, required_version), file = sys.stderr)
            perlversion = None

    return perlversion


def printPKGBUILD(kohaversion: str, perlversion: str, koha_perldeps: list, archpkgs_cache: List[ArchPackage]):
    print(("""\
# Contributor: Bence Csókás <bence98  sch bme hu>

pkgname='koha-perldeps-meta'
pkgver='{0}'
pkgrel='1'
pkgdesc="Koha Integrated Library System (ILS) - Perl dependencies meta-package"
arch=('any')
license=('GPL')
options=('!emptydirs')
depends=(
    'perl>={1}'\
""").format(kohaversion, perlversion));

    archpkgnames = []

    for perlname, installed_version, required_version in koha_perldeps:
        archpkg = list(filter(lambda archpkg: archpkg.perlname == perlname, archpkgs_cache))
        assert len(archpkg) == 1
        archpkg = archpkg[0]

        # Skip all perl-modules that are provided by the perl-ArchPackage.
        if archpkg.name == "perl":
            continue

        archpkgname = archpkg.name
        if list(filter(lambda name: archpkgname == name, archpkgnames)):
            # Some ArchPackages provide multiple perl-modules. So if it was already listed, skip it.
            continue;

        # Some ArchPackages provide multiple perl-modules.
        # In this case take the one with the highest required version.
        archpkgs_equal = list(filter(lambda archpkg: archpkg.name == archpkgname, archpkgs_cache))
        if len(archpkgs_equal) > 1:
            archpkgs_equal.sort(key = lambda archpkg: archpkg.required_version, reverse=True)
            archpkg = archpkgs_equal[0]

        print("    '{0}>={1}'".format(archpkg.name, archpkg.required_version))
        archpkgnames.append(archpkg.name)

    print("""\
)
makedepends=()
url='https://koha-community.org'
""")


def  printAURdeptree(perldeps: list, archpkgs_cache: List[ArchPackage]):
    print("koha-perldeps")

    for perlname, installed_version, required_version in perldeps:
        archpkg = list(filter(lambda archpkg: archpkg.perlname == perlname, archpkgs_cache))
        if not archpkg:
            continue
        assert len(archpkg) >= 1, "No entries found for perl module `" + perlname + "' in cache!?"
        assert len(archpkg) == 1, "Multiple entries found for perl module `" + perlname + "' in cache!?"
        archpkg = archpkg[0]

        printAURdeptree_recursive(0, archpkg.name, archpkgs_cache)


def  printAURdeptree_recursive(level: int, archpkgname: str, archpkgs_cache: List[ArchPackage]):
    #if archpkgname in ["perl", "perl-cgi", "perl-libwww", "perl-digest-sha", "perl-text-balanced"]:
    #    return

    archpkg = list(filter(lambda archpkg: archpkg.name == archpkgname, archpkgs_cache))
    assert len(archpkg) >= 1, "No ArchLinux-packages found for " + archpkgname + " in cache!?"
    assert len(archpkg) == 1, "Multiple ArchLinux-packages found for " + archpkgname + " in cache!?"
    archpkg = archpkg[0]

    if archpkg.repo != "aur":
        return

    FAIL = '\033[91m';
    WARNING = '\033[93m';
    ENDCOLOR = '\033[0m';
    maintainer = archpkg.maintainer if archpkg.maintainer and archpkg.maintainer != "None" else ""
    if not maintainer:
        maintainer = FAIL + "orphan" + ENDCOLOR;

    print(("  " * level) + "- {0} ({1})".format(archpkg.provided_by, maintainer))

    for dep in archpkg.depends:
        (archpkgname, required_version) = dep.split(">=") if len(dep.split(">=")) == 2 else [dep, ""]
        if not archpkgname.startswith("perl-"):
            continue
        printAURdeptree_recursive(level+1, archpkgname, archpkgs_cache)


# ---

def save_cache(filename: str, archpkgs: List[ArchPackage]):
    try:
        file = open(filename, "a")
    except Exception as e:
        print("Error: Can't open `{0}' for writing:".format(filename), e, file = sys.stderr)
    else:
        with file:
            for archpkg in [archpkg for archpkg in archpkgs if not archpkg.cached]:
                perlname = archpkg.perlname
                archpkg_cached = list(filter(lambda archpkg: archpkg.perlname == perlname and archpkg.cached, archpkgs))
                assert not archpkg_cached, "ArchLinux-package for `" + perlname + "' already exist cached!"

                line = serialize(archpkg)
                print(line, file = file)
                archpkg.cached = True

def load_cache(filename: str):
    try:
        if not isfile(filename):
            return []

        file = open(filename, "r")

    except Exception as e:
        print("Error: Can't open `{0}' for reading:".format(filename), e, file = sys.stderr)
    else:
        with file:
            archpkgs = []
            for line in file:
                archpkg = deserialize(line)
                if not archpkg:
                    print("Warning: Strange line encountered `" + line + "'.", file = sys.stderr)
                else:
                    archpkgs.append(archpkg)
            return archpkgs

# ArchPackage(name='perl-cgi-carp', perlname='CGI::Carp', required_version='1.29',\
#   version='4.59', provided_by='perl-cgi', provided_version='4.59',\
#   repo='extra', maintainer='bluewind', depends=['perl>=5.8.1', 'perl-html-parser'])
def serialize(archpkg: ArchPackage):
    dependsstr = ""
    if len(archpkg.depends) > 0:
        dependsstr = "'" + str.join("', '", archpkg.depends) + "'"
    return ("ArchPackage("
            + "name='{0}', perlname='{1}', required_version='{2}', version='{3}', "
            + "provided_by='{4}', provided_version='{5}', "
            + "repo='{6}', maintainer='{7}', depends=[{8}])").format(
                archpkg.name, archpkg.perlname, archpkg.required_version, archpkg.version,
                archpkg.provided_by, archpkg.provided_version,
                archpkg.repo, archpkg.maintainer, dependsstr)


def deserialize(line: str):
    archpkg = []
    pattern = re.compile(r"^ArchPackage\("
            + r"name='([\w\-]+)', perlname='([\w_:]+)', required_version='([\d.]*)', version='([\d.\-_]+)', "
            + r"provided_by='([\w\-]+)', provided_version='([\d.]*)', "
            + r"repo='(\w*)', maintainer='(\w*)', depends=\[([\w\->=.:\+_', ]*)\]"
            + r"\)$")
    dependsstr = ""
    result = pattern.match(line)
    if result:
        archpkg = ArchPackage(result.group(1), result.group(2), result.group(3), result.group(4),
                              result.group(5), result.group(6),
                              result.group(7), result.group(8), [])
        archpkg.cached = True

        dependsstr = result.group(9)
        if dependsstr != "":
            for dep in dependsstr.split(", "):
                result = re.match(r"^'([\w\->=.:\+_]+)'$", dep)
                if not result:
                    return None;

                archpkg.depends.append(result.group(1))

    if not result:
        return None

    return archpkg

# for testing
def CGICarpArchPackage():
    return ArchPackage('perl-cgi-carp', 'CGI::Carp', '1.29',\
        '4.59', 'perl-cgi', '4.59',\
        'extra', 'bluewind', ['perl>=5.8.1', 'perl-html-parser'])


def print_usage_and_exit(errorcode : int = 0):
    print("""\
Usage: {0} <KOHADIR>\
""".format(sys.argv[0]))
    sys.exit(errorcode)

if __name__ == "__main__":
    main()

