import os
import xml.etree.ElementTree as ET

def generate_zone_xml():
    xml_blocks = []
    # Incubator 1: 141-150
    for z in range(1, 11):
        cnl_num = 140 + z
        tag_code = f"Inc1_Zone_{z:02d}"
        name = f"Incubator 01 Zone {z:02d}"
        block = (
            f"  <Cnl>\n"
            f"    <CnlNum>{cnl_num}</CnlNum>\n"
            f"    <Active>true</Active>\n"
            f"    <Name>{name}</Name>\n"
            f"    <Code />\n"
            f"    <DataTypeID xsi:nil=\"true\" />\n"
            f"    <DataLen xsi:nil=\"true\" />\n"
            f"    <CnlTypeID>2</CnlTypeID>\n"
            f"    <ObjNum>1</ObjNum>\n"
            f"    <DeviceNum>1</DeviceNum>\n"
            f"    <TagNum xsi:nil=\"true\" />\n"
            f"    <TagCode>{tag_code}</TagCode>\n"
            f"    <FormulaEnabled>false</FormulaEnabled>\n"
            f"    <InFormula />\n"
            f"    <OutFormula />\n"
            f"    <FormatID>3</FormatID>\n"
            f"    <OutFormatID xsi:nil=\"true\" />\n"
            f"    <QuantityID>4</QuantityID>\n"
            f"    <UnitID>22</UnitID>\n"
            f"    <LimID xsi:nil=\"true\" />\n"
            f"    <ArchiveMask xsi:nil=\"true\" />\n"
            f"    <EventMask>81</EventMask>\n"
            f"  </Cnl>"
        )
        xml_blocks.append(block)

    # Incubator 2: 151-160
    for z in range(1, 11):
        cnl_num = 150 + z
        tag_code = f"Inc2_Zone_{z:02d}"
        name = f"Incubator 02 Zone {z:02d}"
        block = (
            f"  <Cnl>\n"
            f"    <CnlNum>{cnl_num}</CnlNum>\n"
            f"    <Active>true</Active>\n"
            f"    <Name>{name}</Name>\n"
            f"    <Code />\n"
            f"    <DataTypeID xsi:nil=\"true\" />\n"
            f"    <DataLen xsi:nil=\"true\" />\n"
            f"    <CnlTypeID>2</CnlTypeID>\n"
            f"    <ObjNum>1</ObjNum>\n"
            f"    <DeviceNum>1</DeviceNum>\n"
            f"    <TagNum xsi:nil=\"true\" />\n"
            f"    <TagCode>{tag_code}</TagCode>\n"
            f"    <FormulaEnabled>false</FormulaEnabled>\n"
            f"    <InFormula />\n"
            f"    <OutFormula />\n"
            f"    <FormatID>3</FormatID>\n"
            f"    <OutFormatID xsi:nil=\"true\" />\n"
            f"    <QuantityID>4</QuantityID>\n"
            f"    <UnitID>22</UnitID>\n"
            f"    <LimID xsi:nil=\"true\" />\n"
            f"    <ArchiveMask xsi:nil=\"true\" />\n"
            f"    <EventMask>81</EventMask>\n"
            f"  </Cnl>"
        )
        xml_blocks.append(block)

    return "\n".join(xml_blocks)

def update_file(path, add_missing_126_134=False, afoa_content=None):
    with open(path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    closing_tag = "</ArrayOfCnl>"
    if add_missing_126_134 and "<CnlNum>134</CnlNum>" not in content and afoa_content:
        print(f"Adding channels 126-134 to {path}")
        start_126 = afoa_content.find("  <Cnl>\n    <CnlNum>126</CnlNum>")
        end_134 = afoa_content.find("</ArrayOfCnl>")
        missing_block = afoa_content[start_126:end_134]
        pos = content.rfind(closing_tag)
        content = content[:pos] + missing_block + closing_tag

    if "<CnlNum>141</CnlNum>" in content:
        print(f"Channels 141-160 already exist in {path}")
        return content

    pos = content.rfind(closing_tag)
    if pos == -1:
        raise ValueError(f"Closing tag not found in {path}")

    zone_xml = generate_zone_xml()
    new_content = content[:pos] + zone_xml + "\n" + closing_tag

    # Validate XML parsing
    ET.fromstring(new_content)
    print(f"XML validation passed for {path}")

    with open(path, "w", encoding="utf-8-sig") as f:
        f.write(new_content)

    print(f"Updated {path} successfully.")
    return new_content

if __name__ == "__main__":
    afoa_path = r"c:\Projects\labSCADA\rapidSCADAadministratorProjects\Lares_AFOA\BaseXML\Cnl.xml"
    with open(afoa_path, "r", encoding="utf-8-sig") as f:
        afoa_raw = f.read()

    # Update AFOA
    updated_afoa = update_file(afoa_path)

    # Update Demo
    demo_path = r"c:\Projects\labSCADA\rapidSCADAadministratorProjects\Lares_Demo\BaseXML\Cnl.xml"
    update_file(demo_path, add_missing_126_134=True, afoa_content=afoa_raw)

