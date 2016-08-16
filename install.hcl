<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<!DOCTYPE HCL PUBLIC "HCL" "HCL 1.0">
<HCL>
  <SESSION_KEY data=""/>
  <DECLARE>
    <VAR name="ex.stdout" protected="no" transient="no" value=""/>
    <VAR name="ex.stderr" protected="no" transient="no" value=""/>
  </DECLARE>
  <PERFORM>
    <SET value="root" var="defuser"/>
    <SET value="root" var="defgrp"/>
    <EXEC command="/usr/bin/yum" errvar="ex.stderr" group="${defgrp}" outvar="ex.stdout" retvar="" user="${defuser}">
      <ARG protected="no" value="/usr/bin/yum"/>
      <ARG protected="no" value="-y"/>
      <ARG protected="no" value="install"/>
      <ARG protected="no" value="httpd"/>
      <ARG protected="no" value="mod_ssl"/>
    </EXEC>
  </PERFORM>
</HCL>