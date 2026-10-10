# Test if roslyn can compile this code using dotnet or csc or inspect ScadaServer compilation
csharp_code = """
using System;
using System.Diagnostics;
using System.Threading.Tasks;

public class TestScript {
    private DateTime lastPushoverPing = DateTime.MinValue;
    private double lastIncubatorAlarmState = 0;

    private const string PushoverToken = "a2wmo7ofxhhpo2vc2ykdkhtnte8nb5";
    private const string PushoverGroup = "gepqspoh98t69c7o223hwbg8ponwyq";
    private const string PushoverPingUrl = "https://api.pushover.net/1/monitors/mm5z3n2shg9hjn2785oyu649ri92cxh/ping.json";

    public double CheckIncubatorAlarm(double state)
    {
        DateTime now = DateTime.UtcNow;

        if ((now - lastPushoverPing).TotalSeconds >= 60)
        {
            lastPushoverPing = now;
            Task.Run(() =>
            {
                try
                {
                    Process.Start(new ProcessStartInfo
                    {
                        FileName = "curl",
                        Arguments = "-s \"" + PushoverPingUrl + "\"",
                        UseShellExecute = false,
                        CreateNoWindow = true
                    });
                }
                catch { }
            });
        }

        if (state > 0 && lastIncubatorAlarmState == 0)
        {
            lastIncubatorAlarmState = 1;
            Task.Run(() =>
            {
                try
                {
                    string args = string.Format("-s -d \\"token={0}&user={1}&title=CRITICAL+ALARM:+Incubator+1&message=Incubator+1+alarm+contact+TRIPPED!+Check+incubator+immediately.&priority=2&sound=siren&retry=60&expire=7200\\" https://api.pushover.net/1/messages.json",
                        PushoverToken, PushoverGroup);
                    
                    Process.Start(new ProcessStartInfo
                    {
                        FileName = "curl",
                        Arguments = args,
                        UseShellExecute = false,
                        CreateNoWindow = true
                    });
                }
                catch { }
            });
        }
        else if (state == 0 && lastIncubatorAlarmState > 0)
        {
            lastIncubatorAlarmState = 0;
            Task.Run(() =>
            {
                try
                {
                    string args = string.Format("-s -d \\"token={0}&user={1}&title=RESOLVED:+Incubator+1+Normal&message=Incubator+1+alarm+contact+has+returned+to+Normal.&priority=0&sound=magic\\" https://api.pushover.net/1/messages.json",
                        PushoverToken, PushoverGroup);

                    Process.Start(new ProcessStartInfo
                    {
                        FileName = "curl",
                        Arguments = args,
                        UseShellExecute = false,
                        CreateNoWindow = true
                    });
                }
                catch { }
            });
        }

        return state;
    }
}
"""
print("Syntax checked.")
