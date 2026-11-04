import os
import xml.etree.ElementTree as ET

def generate_ups_cnl_xml():
    cnls = [
        (171, "Primary UPS Grid Online", "UPS1_Online", 1, 21, None, None, 5),
        (172, "Primary UPS Battery Charge", "UPS1_BatteryPct", 2, 3, 4, 101, 81),
        (173, "Primary UPS Runtime Remaining", "UPS1_RuntimeMin", 2, 3, 4, 13, 81),
        (174, "Primary UPS Line Voltage", "UPS1_Voltage", 2, 3, 4, 41, 81),
        (175, "Primary UPS Load", "UPS1_LoadPct", 2, 3, 4, 101, 81),
        (176, "Primary UPS Power Lost Alarm", "UPS1_AlarmPowerLost", 1, 21, None, None, 5),
        (177, "Primary UPS Low Battery Alarm", "UPS1_AlarmLowBatt", 1, 21, None, None, 5),
        (178, "Primary UPS Beeper Muted", "UPS1_BeeperMuted", 1, 21, None, None, 5),
        (179, "Primary UPS Mute Beeper Command", "UPS1_CmdMute", 3, 25, None, None, 5),
    ]

    xml_blocks = []
    for cnl_num, name, tag_code, cnl_type, format_id, qty_id, unit_id, event_mask in cnls:
        qty_xml = f"<QuantityID>{qty_id}</QuantityID>" if qty_id else '<QuantityID xsi:nil="true" />'
        unit_xml = f"<UnitID>{unit_id}</UnitID>" if unit_id else '<UnitID xsi:nil="true" />'
        block = (
            f"  <Cnl>\n"
            f"    <CnlNum>{cnl_num}</CnlNum>\n"
            f"    <Active>true</Active>\n"
            f"    <Name>{name}</Name>\n"
            f"    <Code />\n"
            f"    <DataTypeID xsi:nil=\"true\" />\n"
            f"    <DataLen xsi:nil=\"true\" />\n"
            f"    <CnlTypeID>{cnl_type}</CnlTypeID>\n"
            f"    <ObjNum>1</ObjNum>\n"
            f"    <DeviceNum>1</DeviceNum>\n"
            f"    <TagNum xsi:nil=\"true\" />\n"
            f"    <TagCode>{tag_code}</TagCode>\n"
            f"    <FormulaEnabled>false</FormulaEnabled>\n"
            f"    <InFormula />\n"
            f"    <OutFormula />\n"
            f"    <FormatID>{format_id}</FormatID>\n"
            f"    <OutFormatID xsi:nil=\"true\" />\n"
            f"    {qty_xml}\n"
            f"    {unit_xml}\n"
            f"    <LimID xsi:nil=\"true\" />\n"
            f"    <ArchiveMask xsi:nil=\"true\" />\n"
            f"    <EventMask>{event_mask}</EventMask>\n"
            f"  </Cnl>"
        )
        xml_blocks.append(block)
    return "\n".join(xml_blocks)

def update_cnl_file(path):
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return
    with open(path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    if "<CnlNum>171</CnlNum>" in content:
        print(f"Channels 171-179 already exist in {path}")
        return

    closing_tag = "</ArrayOfCnl>"
    pos = content.rfind(closing_tag)
    if pos == -1:
        raise ValueError(f"Closing tag not found in {path}")

    ups_xml = generate_ups_cnl_xml()
    new_content = content[:pos] + ups_xml + "\n" + closing_tag

    # Validate XML
    ET.fromstring(new_content)
    print(f"XML validation passed for {path}")

    with open(path, "w", encoding="utf-8-sig") as f:
        f.write(new_content)
    print(f"Successfully added channels 171-179 to {path}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    update_cnl_file(os.path.join(base_dir, "rapidSCADAadministratorProjects", "Lares_Demo", "BaseXML", "Cnl.xml"))
    update_cnl_file(os.path.join(base_dir, "rapidSCADAadministratorProjects", "Lares_AFOA", "BaseXML", "Cnl.xml"))
