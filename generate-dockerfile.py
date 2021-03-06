#!/usr/bin/python

import argparse

labels = [
    ("com.redhat.component", "openscap-docker"),
    ("name", "openscap"),
    ("version", "testing"),
    ("architecture", "x86_64"),
    ("summary", "OpenSCAP container image that provides security/compliance scanning capabilities for 'atomic scan'"),
    ("description", "OpenSCAP is an auditing tool that utilizes the Extensible Configuration Checklist Description Format (XCCDF). XCCDF is a standard way of expressing checklist content and defines security checklists."),
    ("io.k8s.display-name", "OpenSCAP"),
    ("io.k8s.description", "OpenSCAP is an auditing tool that utilizes the Extensible Configuration Checklist Description Format (XCCDF). XCCDF is a standard way of expressing checklist content and defines security checklists."),
    ("io.openshift.tags", "security openscap scan"),
    ("install", "docker run --rm --privileged -v /:/host/ IMAGE sh /root/install.sh"),
    ("run", "docker run -it --rm -v /:/host/ IMAGE sh /root/run.sh")
]
packages = [
    "bzip2",
    "wget"
]
files = [
    ("container/install.sh", "/root"),
    ("container/run.sh", "/root"),
    ("container/openscap", "/root"),
    ("container/config.ini", "/root"),
    ("container/remediate.py", "/root")
]
env_variables = [
    ("container", "docker")
]
install_commands = {
    "fedora": "dnf",
    "rhel": "yum"
}
builddep_packages = {
    "fedora" : "'dnf-command(builddep)'",
    "rhel" : "yum-utils"
}
builddep_commands = {
    "fedora": "dnf -y builddep",
    "rhel": "yum-builddep -y"
}
download_cve_feeds_command = [
    "wget --no-verbose -P /var/lib/oscapd/cve_feeds/ "
    "https://www.redhat.com/security/data/oval/com.redhat.rhsa-RHEL{5,6,7}.xml.bz2",
    "bzip2 -dk /var/lib/oscapd/cve_feeds/com.redhat.rhsa-RHEL{5,6,7}.xml.bz2",
    "ln -s /var/lib/oscapd/cve_feeds/ /var/tmp/image-scanner"
]
openscap_build_command = [
    "git clone -b maint-1.2 https://github.com/OpenSCAP/openscap.git",
    "pushd /openscap",
    "./autogen.sh",
    "./configure --enable-sce --prefix=/usr",
    "make -j 4 install",
    "popd"
]
ssg_build_command = [
    "git clone https://github.com/OpenSCAP/scap-security-guide.git",
    "pushd /scap-security-guide/build",
    "cmake -DCMAKE_INSTALL_DATADIR=/usr/share ..",
    "make -j 4 install",
    "popd"
]
daemon_local_build_command = [
    "pushd /openscap-daemon",
    "python setup.py install",
    "popd"
]
delim = " && \\\n    "


def main():
    parser = argparse.ArgumentParser(description="Builds an image with OpenSCAP Daemon")
    openscap_group = parser.add_mutually_exclusive_group(required=False)
    ssg_group = parser.add_mutually_exclusive_group(required=False)
    daemon_group = parser.add_mutually_exclusive_group(required=False)
    parser.add_argument("--base", type=str, default="fedora",
            help="Base image name (default is fedora)")
    openscap_group.add_argument("--openscap-from-git", action="store_true",
        default=False, help="Use OpenSCAP from upstream instead of package")
    openscap_group.add_argument("--openscap-from-koji", type=str,
        help="Use OpenSCAP from Koji based on build ID (Fedora only)")
    ssg_group.add_argument("--ssg-from-koji", type=str,
        help="Use SCAP Security Guide from Koji based on build ID (Fedora only)")
    ssg_group.add_argument("--ssg-from-git", action="store_true", default=False,
        help="Use SCAP Security Guide from upstream instead of package")
    daemon_group.add_argument("--daemon-from-local", action="store_true", default=False,
        help="Use OpenSCAP Daemon from local working tree instead of package")
    daemon_group.add_argument("--daemon-from-koji", type=str,
        help="Use OpenSCAP Daemon from Koji based on build ID (Fedora only)")
    args = parser.parse_args()
    if (args.base != "fedora") and (args.openscap_from_koji != None
        or args.ssg_from_koji != None or args.daemon_from_koji != None):
            parser.error("Koji builds can be used only with fedora base image")

    f = open("Dockerfile", "w")

    # Fallback commands are set to RHEL if the configuration
    # for user-defined base is not specified in respective dictionaries.
    # That's because RHEL uses YUM that is older and most wider used.
    install_command = install_commands.get(args.base, install_commands["rhel"])
    builddep_package = builddep_packages.get(args.base, builddep_packages["rhel"])
    builddep_command = builddep_commands.get(args.base, builddep_commands["rhel"])

    # write out the Dockerfile
    f.write("FROM {0}\n\n".format(args.base))

    # add labels
    for name, value in labels:
        f.write("LABEL {0}=\"{1}\"\n".format(name, value))
    f.write("\n")

    # add environment variables
    for var, val in env_variables:
        f.write("ENV {0} {1}\n".format(var, val))
    f.write("\n")

    build_from_source = []
    build_commands = []
    koji_commands = []
    install_from_koji = []

    # OpenSCAP
    if args.openscap_from_git:
        packages.extend(["git", "libtool", "automake"])
        build_from_source.append("openscap")
        build_commands.append(openscap_build_command)
    elif args.openscap_from_koji != None:
        packages.extend(["koji"])
        install_from_koji.append("openscap")
        openscap_koji_command = [
            "koji download-build -a x86_64 {0}".format(args.openscap_from_koji),
            "koji download-build -a noarch {0}".format(args.openscap_from_koji),
            "{0} -y install openscap-[0-9]*.rpm openscap-scanner*.rpm openscap-utils*.rpm openscap-containers*.rpm".format(install_command),
            "rm -f openscap-*.rpm"
        ]
        koji_commands.append(openscap_koji_command)
    else:
        packages.append("openscap-utils")

    # SCAP Security Guide
    if args.ssg_from_git:
        packages.append("git")
        build_from_source.append("scap-security-guide")
        build_commands.append(ssg_build_command)
    elif args.ssg_from_koji != None:
        packages.extend(["koji"])
        install_from_koji.append("scap-security-guide")
        ssg_koji_command = [
            "koji download-build -a noarch {0}".format(args.ssg_from_koji),
            "{0} -y install scap-security-guide-[0-9]*.rpm".format(install_command),
            "rm -f scap-security-guide*.rpm"
        ]
        koji_commands.append(ssg_koji_command)
    else:
        packages.append("scap-security-guide")

    # OpenSCAP Daemon
    if args.daemon_from_local:
        build_from_source.append("openscap-daemon")
        build_commands.append(daemon_local_build_command)
        files.append((".","/openscap-daemon"))
    elif args.daemon_from_koji != None:
        packages.extend(["koji"])
        install_from_koji.append("openscap-daemon")
        daemon_koji_command = [
            "koji download-build -a noarch {0}".format(args.daemon_from_koji),
            "{0} -y install openscap-daemon*.rpm".format(install_command),
            "rm -f openscap-daemon*.rpm"
        ]
        koji_commands.append(daemon_koji_command)
    else:
        packages.append("openscap-daemon")

    # inject files
    for filename, path in files:
        f.write("ADD {0} {1}\n".format(filename, path))
    f.write("\n")

    if build_from_source:
        packages.append(builddep_package)

    if args.base != "fedora":
        f.write("RUN rpm -Uvh https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm\n\n")

    # add a command to install packages
    f.write("RUN {0} -y install {1}\n\n".format(install_command, " ".join(set(packages))))

    if build_from_source:
        # install build dependencies
        f.write("RUN {0} {1}\n\n".format(builddep_command, " ".join(build_from_source)))

    if build_from_source:
        # add commands for building from custom sources
        for cmd in build_commands:
            f.write("RUN {0}\n\n".format(delim.join(cmd)))

    if install_from_koji:
        for cmd in koji_commands:
            f.write("RUN {0}\n\n".format(delim.join(cmd)))

    # add RUN instruction that will download CVE feeds
    f.write("RUN {0}\n\n".format(delim.join(download_cve_feeds_command)))

    # clean package manager cache
    f.write("RUN {0} clean all\n\n".format(install_command))

    # add CMD instruction to the Dockerfile, including a comment
    f.write("# It doesn't matter what is in the line below, atomic will change the CMD\n")
    f.write("# before running it\n")
    f.write('CMD ["/root/run.sh"]\n')

    f.close()

if __name__ == "__main__":
    main()
