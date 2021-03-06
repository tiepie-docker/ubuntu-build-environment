from __future__ import print_function
import os
import sys
import json
from subprocess import check_call
from argparse import ArgumentParser

parser = ArgumentParser()
parser.add_argument('--suite', required=True)
parser.add_argument('--arch', required=True)
parser.add_argument('--qemu-version', required=True)
parser.add_argument('--qemu-arch', required=True)
parser.add_argument('--docker-repo', required=True)
parser.add_argument('--date', required=True)

args = parser.parse_args()

try:
    build_directory = "build"

    if not os.path.exists(build_directory):
        os.mkdir(build_directory)

    # Download image:
    image_file_name = "ubuntu-" + args.suite + "-core-cloudimg-" + args.arch + "-root.tar.gz"
    if not os.path.exists(build_directory + "/" + image_file_name):
        print("Download image file")
        base_url = "https://partner-images.canonical.com/core"
        try:
            check_call(["wget", "-O", build_directory + "/" + image_file_name, base_url + "/" + args.suite + "/current/" + image_file_name])
        except Exception, e:
            print("Failed to download file trying unsupported directory", file=sys.stderr)
            check_call(["wget", "-O", build_directory + "/" + image_file_name, base_url + "/unsupported/" + args.suite + "/current/" + image_file_name])

    # Download qemu:
    qemu_file_name = "qemu-" + args.qemu_arch + "-static"
    if not os.path.exists(build_directory + "/" + qemu_file_name):
        print("Downloading qemu")
        qemu_file_name_tgz = "x86_64_" + qemu_file_name + ".tar.gz"
        check_call(["wget", "-O", qemu_file_name_tgz, "https://github.com/multiarch/qemu-user-static/releases/download/" + args.qemu_version + "/" + qemu_file_name_tgz])
        print("Extracting qemu")
        check_call(["tar", "xvf", qemu_file_name_tgz, "-C", build_directory, qemu_file_name])

    # Read packages-apt.json:
    packages = []
    with open("packages-apt.json") as f:
        data = json.load(f)
        if "all" in data:
            packages += data["all"]
        if args.suite in data:
            if "all" in data[args.suite]:
                packages += data[args.suite]["all"]
            if args.arch in data[args.suite]:
                packages += data[args.suite][args.arch]
        packages = list(set(packages))

    # Read packages-python-pip.json:
    packages_pip = {2: [], 3: []}
    with open("packages-python-pip.json") as f:
        data = json.load(f)
        if "all" in data:
            if "all" in data["all"]:
                for i in [2, 3]:
                    packages_pip[i] += data["all"]["all"]
            for i in [2, 3]:
                p = "python" + str(i)
                if p in data["all"]:
                    packages_pip[i] += data["all"][p]
        if args.suite in data:
            if "all" in data[args.suite]:
                if "all" in data[args.suite]["all"]:
                    for i in [2, 3]:
                        packages_pip[i] += data[args.suite]["all"]["all"]
                if "python2" in data[args.suite]["all"]:
                    packages_pip[2] += data[args.suite]["all"]["python2"]
                if "python3" in data[args.suite]["all"]:
                    packages_pip[3] += data[args.suite]["all"]["python3"]
            if args.arch in data[args.suite]:
                if "all" in data[args.suite][args.arch]:
                    for i in range[2, 3]:
                        packages_pip[i] += data[args.suite][args.arch]["all"]
                if "python2" in data[args.suite][args.arch]:
                    packages_pip[2] += data[args.suite][args.arch]["python2"]
                if "python3" in data[args.suite][args.arch]:
                    packages_pip[3] += data[args.suite][args.arch]["python3"]

    # Create Docker file:
    docker_file = open("build/Dockerfile", "w")
    docker_file.write("FROM scratch\n")
    docker_file.write("\n")

    docker_file.write("ADD " + image_file_name + " /\n")
    docker_file.write("ADD " + qemu_file_name + " /usr/bin/\n")
    docker_file.write("\n")

    docker_file.write("ENV DEBIAN_FRONTEND=noninteractive\n")
    docker_file.write("ENV DEBCONF_NONINTERACTIVE_SEEN=true\n")
    docker_file.write("\n")

    docker_file.write("RUN set -xe && \\\n")
    docker_file.write("    echo '#!/bin/sh' > /usr/sbin/policy-rc.d && \\\n")
    docker_file.write("    echo 'exit 101' >> /usr/sbin/policy-rc.d && \\\n")
    docker_file.write("    chmod +x /usr/sbin/policy-rc.d && \\\n")
    docker_file.write("    dpkg-divert --local --rename --add /sbin/initctl && \\\n")
    docker_file.write("    cp -a /usr/sbin/policy-rc.d /sbin/initctl && \\\n")
    docker_file.write("    sed -i 's/^exit.*/exit 0/' /sbin/initctl && \\\n")
    docker_file.write("    echo 'force-unsafe-io' > /etc/dpkg/dpkg.cfg.d/docker-apt-speedup && \\\n")
    docker_file.write("    echo 'DPkg::Post-Invoke { \"rm -f /var/cache/apt/archives/*.deb /var/cache/apt/archives/partial/*.deb /var/cache/apt/*.bin || true\"; };' > /etc/apt/apt.conf.d/docker-clean && \\\n")
    docker_file.write("    echo 'APT::Update::Post-Invoke { \"rm -f /var/cache/apt/archives/*.deb /var/cache/apt/archives/partial/*.deb /var/cache/apt/*.bin || true\"; };' >> /etc/apt/apt.conf.d/docker-clean && \\\n")
    docker_file.write("    echo 'Dir::Cache::pkgcache \"\"; Dir::Cache::srcpkgcache \"\";' >> /etc/apt/apt.conf.d/docker-clean && \\\n")
    docker_file.write("    echo 'Acquire::Languages \"none\";' > /etc/apt/apt.conf.d/docker-no-languages && \\\n")
    docker_file.write("    echo 'Acquire::GzipIndexes \"true\"; Acquire::CompressionTypes::Order:: \"gz\";' > /etc/apt/apt.conf.d/docker-gzip-indexes && \\\n")
    docker_file.write("    echo 'Apt::AutoRemove::SuggestsImportant \"false\";' > /etc/apt/apt.conf.d/docker-autoremove-suggests && \\\n")
    docker_file.write("    apt-get clean && \\\n")
    docker_file.write("    rm -rf /var/lib/apt/lists/*\n")
    docker_file.write("\n")

    docker_file.write("RUN apt-get update && \\\n")
    docker_file.write("    apt-get dist-upgrade -y && \\\n")
    docker_file.write("    apt-get install -y apt-utils && \\\n")
    docker_file.write("    apt-get clean && \\\n")
    docker_file.write("    rm -rf /var/lib/apt/lists/*\n")
    docker_file.write("\n")

    if packages:
        docker_file.write("RUN apt-get update && \\\n")
        docker_file.write("    apt-get install -y " + (" \\\n" + " " * 23).join(packages) + " && \\\n")
        docker_file.write("    apt-get clean && \\\n")
        docker_file.write("    rm -rf /var/lib/apt/lists/*\n")
        docker_file.write("\n")

    if args.suite == "xenial" and args.arch in ["i386", "amd64"]:
        docker_file.write("RUN wget -nv --content-disposition https://packagecloud.io/github/git-lfs/packages/ubuntu/xenial/git-lfs_2.3.4_" + args.arch + ".deb/download.deb && \\\n")
        docker_file.write("    dpkg -i git-lfs_2.3.4_" + args.arch + ".deb && \\\n")
        docker_file.write("    rm git-lfs_2.3.4_" + args.arch + ".deb\n")
        docker_file.write("\n")

    for i in [2, 3]:
        docker_file.write("RUN pip" + str(i) + " --no-cache-dir install " + (" \\\n" + " " * 32).join(packages_pip[i]) + "\n")
        docker_file.write("\n")

    docker_file.write("CMD [\"/bin/bash\"]\n")
    docker_file.write("\n")

    docker_file.close()

    # Build Docker image:
    check_call(["sudo", "docker", "build", "-t", args.docker_repo + ":" + args.arch + "-" + args.suite, "-t", args.docker_repo + ":" + args.arch + "-" + args.suite + "-" + args.date, "build"])

except Exception, e:
    print(str(e), file=sys.stderr)
    sys.exit(1)

sys.exit(0)
