import requests as req

headers={
	'User-Agent': 'CpanBot/1.0 '+req.utils.default_user_agent()
}

license_equiv={
	"perl_5": "'PerlArtistic' 'GPL'",
	"apache_1_1": "'Apache 1.1'",
	"apache_2_0": "'Apache 2.0'",
	"artistic_1": "'PerlArtistic'",
	"artistic_2": "'Artistic2.0'",
	"agpl_3": "'AGPL3'",
	"gpl_2": "'GPL2'",
	"gpl_3": "'GPL3'",
	"lgpl_2_1": "'LGPL2'",
	"lgpl_3_0": "'LGPL3'",
	"gfdl_1_2": "'FDL1.2'",
	"gfdl_1_3": "'FDL1.3'",
	# TODO check these!
	"mozilla_1_0": "'MPL 1.0'",
	"mozilla_1_1": "'MPL 1.1'",
	# TODO these are custom!
	"gpl_1": "'custom:GPLv1'",
	"openssl": "'custom:OpenSSL License'",
	"qpl_1_0": "'custom:Q Public License, Version 1.0'",
	"ssleay": "'custom:Original SSLeay License'",
	"sun": "'custom:Sun Internet Standards Source License (SISSL)'",
	# TODO these are technically custom
	"freebsd": "'BSD'",
	"mit": "'MIT'",
	"zlib": "'ZLIB'",
	"bsd": "'BSD'" # TODO this is technically custom
}

def xlate_lic(lic: str) -> str:
	return " ".join((license_equiv[l] for l in lic))

def aur_get_url(pkg_name: str) -> str:
	r=req.get("https://aur.archlinux.org/rpc/v5/info/"+pkg_name, headers=headers)
	r.raise_for_status()
	aurdata=r.json()

	if aurdata["resultcount"]<1:
		raise KeyError("No package named '{0}' found on AUR!".format(pkg_name))
	return aurdata["results"][0]["URL"]

def aur_get_release_name(pkg_name: str) -> str:
	return aur_get_url(pkg_name).strip('/').split('/')[-1]

def cpan_get_release_info(cpan_name: str, cpan_type: str="release"):
	return cpan_api_get(cpan_name, cpan_type)

def cpan_api_get(cpan_name: str, cpan_type: str, params: str=None):
	cpan_url="https://fastapi.metacpan.org/v1/"+cpan_type+"/"+cpan_name
	if params:
		cpan_url+="?"+params
	r=req.get(cpan_url, headers=headers)
	r.raise_for_status()
	return r.json()

def cpan_module_to_release(cpan_module: str) -> (str, str):
	cpan_release=cpan_api_get(cpan_module, "module", "fields=release")["release"]
	return cpan_release[:cpan_release.rindex('-')], cpan_release[cpan_release.rindex('-')+1:]
