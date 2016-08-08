#!/bin/bash
############### OSA installation shell script
############### run it on LINMN

usage() { echo "Usage: $0 -p PCPPASSWD -i MNIP -h MNFQDN" 1>&2; exit 1; }

while getopts ":p:i:h:d:" option; do
    case "${option}" in
    	p)
			PCPPASSWD=${OPTARG}
			;;
		i)
			MNIP=${OPTARG}
			;;
		h)
			MNFQDN=${OPTARG}
			;;
		*)
			usage
			;;
	esac
done
shift $(($OPTIND - 1))
if [ -z "${PCPPASSWD}" ] || [ -z "${MNIP}" ] || [ -z "${MNFQDN}" ]; then
    usage
fi

############ Optionally customized
DISTR=/root/distr
POATARURL=https://USER:PASSWORD@download.automation.odin.com/oa/7.0/7.0-release/oa-7.0-9781.tar
MNMODULES="Linux Shared, APS, PBA"

############ Do not touch below
POATAR=$DISTR/${POATARURL##*/}
POADIR=${POATAR%.tar}
INSTALLPY=${POADIR}/install.py
PAUPDATER=/usr/local/pem/bin/pa_updates_installer

# download OA distribution
if [ ! -d "$DISTR" ]; then
	mkdir $DISTR
fi

if [ ! -f "$DISTR/oa-7.0-9781.tar" ]; then
	wget --no-check-certificate --continue --directory-prefix=$DISTR $POATARURL
	tar --extract --file=$POATAR --directory=$DISTR
fi

###### prereqs
# remove uncompatible java rpms
rpm -qa '*openjdk*' 'jdk' | xargs rpm -e
# update OS
yum update -y
# make sure MN hostname resolves propery
if [ -z "$(grep "$MNIP $MNFQDN" /etc/hosts)" ]; then
	echo $MNIP $MNFQDN >> /etc/hosts
fi


# run installer
chmod +x $INSTALLPY

$INSTALLPY --batch --communication_ip ${MNIP} --external_ip ${MNIP} --modules="${MNMODULES}" --hostname=${MNFQDN} --username=admin --password="${PCPPASSWD}" --email=admin@${MNFQDN} --database_host=${MNIP}

systemctl enable httpd.service

# install updates
#${PAUPDATER} --install
