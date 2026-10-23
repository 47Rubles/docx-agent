<?xml version="1.0" encoding="UTF-8"?>
<!-- Bundled basic MathML->OMML stylesheet; supports identifiers, operators, fractions, superscripts, subscripts and roots. Replace with Microsoft's full MML2OMML.XSL for advanced math. -->
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform" xmlns:ml="http://www.w3.org/1998/Math/MathML" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
<xsl:output method="xml" encoding="UTF-8"/>
<xsl:template match="/"><m:oMath><xsl:apply-templates/></m:oMath></xsl:template>
<xsl:template match="ml:math|ml:mrow|ml:mstyle|ml:semantics"><xsl:apply-templates/></xsl:template>
<xsl:template match="ml:mi|ml:mn|ml:mo|ml:mtext|ml:ms"><m:r><m:t><xsl:value-of select="."/></m:t></m:r></xsl:template>
<xsl:template match="ml:mfrac"><m:f><m:num><xsl:apply-templates select="*[1]"/></m:num><m:den><xsl:apply-templates select="*[2]"/></m:den></m:f></xsl:template>
<xsl:template match="ml:msup"><m:sSup><m:e><xsl:apply-templates select="*[1]"/></m:e><m:sup><xsl:apply-templates select="*[2]"/></m:sup></m:sSup></xsl:template>
<xsl:template match="ml:msub"><m:sSub><m:e><xsl:apply-templates select="*[1]"/></m:e><m:sub><xsl:apply-templates select="*[2]"/></m:sub></m:sSub></xsl:template>
<xsl:template match="ml:msubsup"><m:sSubSup><m:e><xsl:apply-templates select="*[1]"/></m:e><m:sub><xsl:apply-templates select="*[2]"/></m:sub><m:sup><xsl:apply-templates select="*[3]"/></m:sup></m:sSubSup></xsl:template>
<xsl:template match="ml:msqrt"><m:rad><m:deg/><m:e><xsl:apply-templates/></m:e></m:rad></xsl:template>
<xsl:template match="ml:mroot"><m:rad><m:deg><xsl:apply-templates select="*[2]"/></m:deg><m:e><xsl:apply-templates select="*[1]"/></m:e></m:rad></xsl:template>
<xsl:template match="ml:annotation"/>
<xsl:template match="*"><xsl:apply-templates/></xsl:template>
</xsl:stylesheet>
