# cpan2aur2git
CPAN2AUR2Git bot (CpanBot)

## What this project is

`cpan2aur` was written a long time ago, when the CPAN operated by uploading tarballs to an FTP server. This project takes those tarballs and creates and pushes the Git commits to the new AUR.

## How to use

1. Set up Git and SSH to be able to push to the AUR. See [the Arch wiki](https://wiki.archlinux.org/title/AUR_submission_guidelines#Authentication) for details
2. Install and set up [`perl-cpanplus-dist-arch`](https://archlinux.org/packages/extra/any/perl-cpanplus-dist-arch/) (for `cpan2aur` command)
3. Usage: `./cpan2aur2git <Perl::Pkg::Name>`
