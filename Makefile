#!/usr/bin/make -f

PREFIX=/usr

BINDIR=${DESTDIR}${PREFIX}/bin
SVCDIR=${DESTDIR}${PREFIX}/lib/systemd/system

BINARIES=cpan2aur2git aur2cpan-name cpanbot-daemon cpanbot-mail
SERVICES=cpanbot-daemon.service

INSTALLED_FILES=$(foreach bin, ${BINARIES}, ${BINDIR}/${bin})
INSTALLED_FILES+=$(foreach svc, ${SERVICES}, ${SVCDIR}/${svc})

test:
	@echo "Not yet implemented"

install: ${INSTALLED_FILES}

uninstall:
	rm -rf ${INSTALLED_FILES}
	rmdir --ignore-fail-on-non-empty -p ${BINDIR} ${SVCDIR}

${BINDIR}/%: %
	install -D $< $@

${SVCDIR}/%: %
	install -Dm 444 $< $@
