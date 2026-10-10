using System;
using System.Reflection;

class Program {
    static void Main() {
        var asm = Assembly.LoadFrom("/opt/scada/ScadaComm/ScadaCommon.dll");
        foreach (var type in asm.GetTypes()) {
            if (type.Name.Contains("ScadaUtils") || type.Name.Contains("Agent") || type.Name.Contains("SecretKey")) {
                Console.WriteLine("Type: " + type.FullName);
                foreach (var m in type.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance)) {
                    if (m.Name.Contains("SecretKey") || m.Name.Contains("Hex")) {
                        Console.WriteLine("  Method: " + m.Name);
                    }
                }
            }
        }
    }
}
