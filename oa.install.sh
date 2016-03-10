#!/bin/bash
############### OSA installation shell script
############### run it on LINMN

############ Should be customized
PCPPASSWD=secret1
MNIP=MN.BACK.NET.IP
MNFQDN=MN.HOSTN.AME
POATARURL=http://internal.local/poa-6.0-3517.tar

############ Optionally customized
DISTR=/root/distr
MNMODULES="Linux Shared, APS"
# set below to True, if resintall is needed
REINSTALL=False

############ Do not touch below
POATAR=$DISTR/${POATARURL##*/}
POADIR=${POATAR%.tar}
INSTALLPY=${POADIR}/install.py
PAUPDATER=/usr/local/pem/bin/pa_updates_installer

if [ $REINSTALL == "True" ]; then
	REINSTALL_SWITCH="--reinstall"
else
	REINSTALL_SWITCH=""
fi

# stop on errors
set -e

# download OA distribution
mkdir $DISTR
wget --continue --directory-prefix=$DISTR $POATARURL
tar --extract --file=$POATAR --directory=$DISTR

###### prereqs
# remove uncompatible java rpms
rpm -qa '*openjdk*' 'jdk' | xargs --no-run-if-empty rpm -e
# update OS
yum update -y
# make sure MN hostname resolves propery
echo $MNIP $MNFQDN >> /etc/hosts

# run installer
chmod +x $INSTALLPY

$INSTALLPY --batch $REINSTALL_SWITCH --communication_ip ${MNIP} --external_ip ${MNIP} --modules="${MNMODULES}" --hostname=${MNFQDN} --username=admin --password="${PCPPASSWD}" --email=admin@${MNFQDN} --database_host=${MNIP}

chkconfig httpd on

# install updates
${PAUPDATER} --install

