using System;
using System.Collections.Generic;
using System.Drawing;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.WebSockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using System.Windows.Automation;

namespace ControlMouseCSharp
{
    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
        }
    }

    internal sealed class MainForm : Form
    {
        private const string DefaultServer = "https://your-domain.example";

        private readonly TextBox serverBox = new TextBox();
        private readonly TextBox usernameBox = new TextBox();
        private readonly TextBox passwordBox = new TextBox();
        private readonly TextBox deviceNameBox = new TextBox();
        private readonly Label statusLabel = new Label();
        private readonly Button loginButton = new Button();
        private readonly Button registerButton = new Button();
        private readonly Button offlineButton = new Button();
        private readonly JavaScriptSerializer json = new JavaScriptSerializer();

        private CancellationTokenSource cancelSource;
        private Task workerTask;
        private string token;

        public MainForm()
        {
            Text = "手机鼠标电脑端";
            StartPosition = FormStartPosition.CenterScreen;
            MinimumSize = new Size(500, 430);
            Size = new Size(520, 450);
            Font = new Font("Microsoft YaHei UI", 10F, FontStyle.Regular, GraphicsUnit.Point);
            BackColor = Color.FromArgb(245, 247, 250);

            BuildUi();
            FormClosing += delegate { StopClient(); };
        }

        private void BuildUi()
        {
            var title = new Label
            {
                Text = "电脑端控制服务",
                AutoSize = true,
                Font = new Font(Font.FontFamily, 18F, FontStyle.Bold),
                Location = new Point(28, 24)
            };
            Controls.Add(title);

            AddField("服务器", serverBox, 78, DefaultServer);
            AddField("用户名", usernameBox, 128, "");
            AddField("密码", passwordBox, 178, "");
            passwordBox.UseSystemPasswordChar = true;
            AddField("电脑名称", deviceNameBox, 228, Environment.MachineName);

            loginButton.Text = "登录并上线";
            loginButton.Location = new Point(28, 292);
            loginButton.Size = new Size(135, 42);
            loginButton.Click += async delegate { await LoginAndStartAsync(); };
            Controls.Add(loginButton);

            registerButton.Text = "注册账号";
            registerButton.Location = new Point(178, 292);
            registerButton.Size = new Size(120, 42);
            registerButton.Click += async delegate { await RegisterAsync(); };
            Controls.Add(registerButton);

            offlineButton.Text = "下线";
            offlineButton.Enabled = false;
            offlineButton.Location = new Point(313, 292);
            offlineButton.Size = new Size(105, 42);
            offlineButton.Click += delegate { StopClient(); };
            Controls.Add(offlineButton);

            statusLabel.Text = "状态：未上线";
            statusLabel.AutoEllipsis = true;
            statusLabel.Location = new Point(28, 356);
            statusLabel.Size = new Size(445, 34);
            Controls.Add(statusLabel);
        }

        private void AddField(string labelText, TextBox box, int y, string value)
        {
            var label = new Label
            {
                Text = labelText,
                Location = new Point(28, y + 4),
                Size = new Size(92, 28),
                TextAlign = ContentAlignment.MiddleLeft
            };
            Controls.Add(label);

            box.Text = value;
            box.Location = new Point(122, y);
            box.Size = new Size(350, 30);
            Controls.Add(box);
        }

        private async Task RegisterAsync()
        {
            try
            {
                SetBusy(true, "正在注册...");
                await Task.Run(delegate
                {
                    PostJson(ApiUrl("/api/register"), new Dictionary<string, object>
                    {
                        {"username", usernameBox.Text.Trim()},
                        {"password", passwordBox.Text}
                    });
                });
                SetStatus("注册成功，可以登录上线");
            }
            catch (Exception ex)
            {
                SetStatus("注册失败：" + CleanError(ex.Message));
            }
            finally
            {
                SetBusy(false, null);
            }
        }

        private async Task LoginAndStartAsync()
        {
            try
            {
                StopClient();
                SetBusy(true, "正在登录...");
                var result = await Task.Run(delegate
                {
                    return PostJson(ApiUrl("/api/login"), new Dictionary<string, object>
                    {
                        {"username", usernameBox.Text.Trim()},
                        {"password", passwordBox.Text}
                    });
                });

                token = Convert.ToString(result["token"]);
                cancelSource = new CancellationTokenSource();
                workerTask = Task.Run(delegate { RunWebSocketLoop(cancelSource.Token).Wait(); });
                offlineButton.Enabled = true;
                SetStatus("已登录，正在连接服务器...");
            }
            catch (Exception ex)
            {
                SetStatus("登录失败：" + CleanError(ex.Message));
            }
            finally
            {
                SetBusy(false, null);
            }
        }

        private async Task RunWebSocketLoop(CancellationToken cancel)
        {
            var deviceName = string.IsNullOrWhiteSpace(deviceNameBox.Text) ? Environment.MachineName : deviceNameBox.Text.Trim();
            var url = BuildWebSocketUrl(deviceName);

            while (!cancel.IsCancellationRequested)
            {
                var shouldDelay = false;
                using (var socket = new ClientWebSocket())
                {
                    try
                    {
                        SetStatus("正在连接：" + url.Host);
                        await socket.ConnectAsync(url, cancel);
                        SetStatus("已上线：" + deviceName);

                        using (var linkedCancel = CancellationTokenSource.CreateLinkedTokenSource(cancel))
                        {
                            var focusTask = MonitorInputFocusAsync(socket, linkedCancel.Token);
                        var buffer = new byte[64 * 1024];
                        while (socket.State == WebSocketState.Open && !cancel.IsCancellationRequested)
                        {
                            var text = await ReceiveTextAsync(socket, buffer, cancel);
                            if (!string.IsNullOrEmpty(text))
                            {
                                HandleServerMessage(text);
                            }
                        }
                            linkedCancel.Cancel();
                        }
                    }
                    catch (OperationCanceledException)
                    {
                        break;
                    }
                    catch (Exception ex)
                    {
                        SetStatus("连接断开，3 秒后重试：" + CleanError(ex.Message));
                        shouldDelay = true;
                    }
                }

                if (shouldDelay && !cancel.IsCancellationRequested)
                {
                    await Task.Delay(3000, cancel).ContinueWith(delegate { });
                }
            }
        }

        private async Task<string> ReceiveTextAsync(ClientWebSocket socket, byte[] buffer, CancellationToken cancel)
        {
            var bytes = new List<byte>();
            WebSocketReceiveResult result;
            do
            {
                result = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), cancel);
                if (result.MessageType == WebSocketMessageType.Close)
                {
                    return null;
                }
                for (var i = 0; i < result.Count; i++)
                {
                    bytes.Add(buffer[i]);
                }
            }
            while (!result.EndOfMessage);

            return Encoding.UTF8.GetString(bytes.ToArray());
        }

        private void HandleServerMessage(string text)
        {
            var data = json.Deserialize<Dictionary<string, object>>(text);
            object type;
            if (!data.TryGetValue("type", out type) || Convert.ToString(type) != "command")
            {
                return;
            }

            object command;
            if (data.TryGetValue("command", out command))
            {
                MouseController.RunCommand(command as Dictionary<string, object>);
            }
        }

        private async Task MonitorInputFocusAsync(ClientWebSocket socket, CancellationToken cancel)
        {
            bool? lastActive = null;
            var lastHeartbeat = DateTime.UtcNow;
            while (!cancel.IsCancellationRequested && socket.State == WebSocketState.Open)
            {
                var active = IsTextInputFocused();
                if (lastActive == null || active != lastActive.Value)
                {
                    lastActive = active;
                    await SendJsonAsync(socket, new Dictionary<string, object>
                    {
                        {"type", "inputFocus"},
                        {"active", active}
                    }, cancel);
                }
                if ((DateTime.UtcNow - lastHeartbeat).TotalSeconds >= 15)
                {
                    lastHeartbeat = DateTime.UtcNow;
                    await SendJsonAsync(socket, new Dictionary<string, object>
                    {
                        {"type", "heartbeat"}
                    }, cancel);
                }
                await Task.Delay(350, cancel).ContinueWith(delegate { });
            }
        }

        private static bool IsTextInputFocused()
        {
            try
            {
                var element = AutomationElement.FocusedElement;
                if (element == null)
                {
                    return false;
                }

                var controlType = element.Current.ControlType;
                if (controlType == ControlType.Edit || controlType == ControlType.Document)
                {
                    return true;
                }

                object pattern;
                return element.TryGetCurrentPattern(ValuePattern.Pattern, out pattern)
                    || element.TryGetCurrentPattern(TextPattern.Pattern, out pattern);
            }
            catch
            {
                return false;
            }
        }

        private async Task SendJsonAsync(ClientWebSocket socket, Dictionary<string, object> payload, CancellationToken cancel)
        {
            if (socket.State != WebSocketState.Open)
            {
                return;
            }
            var body = Encoding.UTF8.GetBytes(json.Serialize(payload));
            await socket.SendAsync(new ArraySegment<byte>(body), WebSocketMessageType.Text, true, cancel);
        }

        private Dictionary<string, object> PostJson(string url, Dictionary<string, object> payload)
        {
            var body = Encoding.UTF8.GetBytes(json.Serialize(payload));
            var request = (HttpWebRequest)WebRequest.Create(url);
            request.Method = "POST";
            request.ContentType = "application/json; charset=utf-8";
            request.ContentLength = body.Length;
            request.Timeout = 10000;

            using (var stream = request.GetRequestStream())
            {
                stream.Write(body, 0, body.Length);
            }

            try
            {
                using (var response = (HttpWebResponse)request.GetResponse())
                using (var stream = response.GetResponseStream())
                using (var reader = new System.IO.StreamReader(stream, Encoding.UTF8))
                {
                    return json.Deserialize<Dictionary<string, object>>(reader.ReadToEnd());
                }
            }
            catch (WebException ex)
            {
                var response = ex.Response as HttpWebResponse;
                if (response == null)
                {
                    throw;
                }
                using (var stream = response.GetResponseStream())
                using (var reader = new System.IO.StreamReader(stream, Encoding.UTF8))
                {
                    throw new InvalidOperationException((int)response.StatusCode + " " + reader.ReadToEnd());
                }
            }
        }

        private string ApiUrl(string path)
        {
            return serverBox.Text.Trim().TrimEnd('/') + path;
        }

        private Uri BuildWebSocketUrl(string deviceName)
        {
            var server = new Uri(serverBox.Text.Trim().TrimEnd('/'));
            var builder = new UriBuilder(server);
            builder.Scheme = server.Scheme == "https" ? "wss" : "ws";
            builder.Path = server.AbsolutePath.TrimEnd('/') + "/ws";
            builder.Query =
                "role=desktop" +
                "&token=" + Uri.EscapeDataString(token) +
                "&device_id=" + Uri.EscapeDataString(GetDeviceId()) +
                "&device_name=" + Uri.EscapeDataString(deviceName);
            return builder.Uri;
        }

        private static string GetDeviceId()
        {
            foreach (var item in NetworkInterface.GetAllNetworkInterfaces())
            {
                if (item.OperationalStatus == OperationalStatus.Up)
                {
                    var address = item.GetPhysicalAddress().ToString();
                    if (!string.IsNullOrEmpty(address))
                    {
                        return address;
                    }
                }
            }
            return Environment.MachineName;
        }

        private void StopClient()
        {
            if (cancelSource != null)
            {
                cancelSource.Cancel();
                cancelSource.Dispose();
                cancelSource = null;
            }
            token = null;
            offlineButton.Enabled = false;
            SetStatus("状态：未上线");
        }

        private void SetBusy(bool busy, string message)
        {
            loginButton.Enabled = !busy;
            registerButton.Enabled = !busy;
            serverBox.Enabled = !busy;
            usernameBox.Enabled = !busy;
            passwordBox.Enabled = !busy;
            deviceNameBox.Enabled = !busy;
            if (!string.IsNullOrEmpty(message))
            {
                SetStatus(message);
            }
        }

        private void SetStatus(string text)
        {
            if (statusLabel.InvokeRequired)
            {
                BeginInvoke(new Action<string>(SetStatus), text);
                return;
            }
            statusLabel.Text = text.StartsWith("状态：") ? text : "状态：" + text;
        }

        private static string CleanError(string message)
        {
            if (string.IsNullOrWhiteSpace(message))
            {
                return "未知错误";
            }

            if (message.Contains("user_exists"))
            {
                return "账号已存在，请直接登录或换一个用户名";
            }
            if (message.Contains("invalid_credentials"))
            {
                return "账号或密码错误";
            }
            if (message.Contains("invalid_input"))
            {
                return "用户名至少 3 位，密码至少 6 位";
            }

            return message.Replace("\r", " ").Replace("\n", " ");
        }
    }

    internal static class MouseController
    {
        private const uint INPUT_MOUSE = 0;
        private const uint INPUT_KEYBOARD = 1;
        private const uint MOUSEEVENTF_MOVE = 0x0001;
        private const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
        private const uint MOUSEEVENTF_LEFTUP = 0x0004;
        private const uint MOUSEEVENTF_RIGHTDOWN = 0x0008;
        private const uint MOUSEEVENTF_RIGHTUP = 0x0010;
        private const uint MOUSEEVENTF_MIDDLEDOWN = 0x0020;
        private const uint MOUSEEVENTF_MIDDLEUP = 0x0040;
        private const uint MOUSEEVENTF_WHEEL = 0x0800;
        private const uint KEYEVENTF_KEYUP = 0x0002;
        private const uint KEYEVENTF_UNICODE = 0x0004;
        private const ushort VK_CONTROL = 0x11;
        private const ushort VK_RETURN = 0x0D;
        private const ushort VK_ESCAPE = 0x1B;
        private const ushort VK_ADD = 0x6B;
        private const ushort VK_SUBTRACT = 0x6D;
        private const ushort VK_C = 0x43;
        private const ushort VK_S = 0x53;
        private const ushort VK_V = 0x56;
        private const ushort VK_Z = 0x5A;

        private static double remainderX;
        private static double remainderY;

        [DllImport("user32.dll")]
        private static extern bool GetCursorPos(out POINT point);

        [DllImport("user32.dll")]
        private static extern bool SetCursorPos(int x, int y);

        [DllImport("user32.dll", SetLastError = true)]
        private static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

        public static void RunCommand(Dictionary<string, object> command)
        {
            if (command == null || !command.ContainsKey("type"))
            {
                return;
            }

            var type = Convert.ToString(command["type"]);
            if (type == "move")
            {
                MoveCursor(Number(command, "dx"), Number(command, "dy"));
            }
            else if (type == "click")
            {
                Click(Text(command, "button", "left"));
            }
            else if (type == "doubleClick")
            {
                Click(Text(command, "button", "left"));
                Click(Text(command, "button", "left"));
            }
            else if (type == "mouseDown")
            {
                MouseDown(Text(command, "button", "left"));
            }
            else if (type == "mouseUp")
            {
                MouseUp(Text(command, "button", "left"));
            }
            else if (type == "scroll")
            {
                Wheel((int)Number(command, "delta"));
            }
            else if (type == "zoom")
            {
                Hotkey(VK_CONTROL, Number(command, "delta") > 0 ? VK_ADD : VK_SUBTRACT);
            }
            else if (type == "hotkey")
            {
                SendHotkey(Text(command, "name", ""));
            }
            else if (type == "key")
            {
                SendKey(Text(command, "name", ""));
            }
            else if (type == "text")
            {
                SendText(Text(command, "value", ""));
            }
        }

        private static void MoveCursor(double dx, double dy)
        {
            POINT point;
            if (!GetCursorPos(out point))
            {
                return;
            }

            var totalX = dx + remainderX;
            var totalY = dy + remainderY;
            var wholeX = (int)totalX;
            var wholeY = (int)totalY;
            remainderX = totalX - wholeX;
            remainderY = totalY - wholeY;

            if (wholeX != 0 || wholeY != 0)
            {
                SetCursorPos(point.X + wholeX, point.Y + wholeY);
            }
        }

        private static void Click(string button)
        {
            MouseDown(button);
            MouseUp(button);
        }

        private static void MouseDown(string button)
        {
            MouseButton(button, true);
        }

        private static void MouseUp(string button)
        {
            MouseButton(button, false);
        }

        private static void MouseButton(string button, bool down)
        {
            uint flags;
            if (button == "right")
            {
                flags = down ? MOUSEEVENTF_RIGHTDOWN : MOUSEEVENTF_RIGHTUP;
            }
            else if (button == "middle")
            {
                flags = down ? MOUSEEVENTF_MIDDLEDOWN : MOUSEEVENTF_MIDDLEUP;
            }
            else
            {
                flags = down ? MOUSEEVENTF_LEFTDOWN : MOUSEEVENTF_LEFTUP;
            }
            SendMouse(flags, 0);
        }

        private static void Wheel(int delta)
        {
            SendMouse(MOUSEEVENTF_WHEEL, delta);
        }

        private static void SendMouse(uint flags, int data)
        {
            var input = new INPUT();
            input.Type = INPUT_MOUSE;
            input.U.Mouse = new MOUSEINPUT { Flags = flags, MouseData = data };
            SendInput(1, new[] { input }, Marshal.SizeOf(typeof(INPUT)));
        }

        private static void SendHotkey(string name)
        {
            if (name == "copy")
            {
                Hotkey(VK_CONTROL, VK_C);
            }
            else if (name == "paste")
            {
                Hotkey(VK_CONTROL, VK_V);
            }
            else if (name == "undo")
            {
                Hotkey(VK_CONTROL, VK_Z);
            }
            else if (name == "save")
            {
                Hotkey(VK_CONTROL, VK_S);
            }
        }

        private static void SendKey(string name)
        {
            if (name == "enter")
            {
                Key(VK_RETURN);
            }
            else if (name == "escape")
            {
                Key(VK_ESCAPE);
            }
        }

        private static void Hotkey(ushort modifier, ushort key)
        {
            SendInput(4, new[] { KeyInput(modifier, false), KeyInput(key, false), KeyInput(key, true), KeyInput(modifier, true) }, Marshal.SizeOf(typeof(INPUT)));
        }

        private static void Key(ushort key)
        {
            SendInput(2, new[] { KeyInput(key, false), KeyInput(key, true) }, Marshal.SizeOf(typeof(INPUT)));
        }

        private static void SendText(string text)
        {
            if (string.IsNullOrEmpty(text))
            {
                return;
            }

            var inputs = new List<INPUT>();
            foreach (var ch in text)
            {
                inputs.Add(UnicodeInput(ch, false));
                inputs.Add(UnicodeInput(ch, true));
            }
            SendInput((uint)inputs.Count, inputs.ToArray(), Marshal.SizeOf(typeof(INPUT)));
        }

        private static INPUT KeyInput(ushort key, bool up)
        {
            var input = new INPUT();
            input.Type = INPUT_KEYBOARD;
            input.U.Keyboard = new KEYBDINPUT { Vk = key, Flags = up ? KEYEVENTF_KEYUP : 0 };
            return input;
        }

        private static INPUT UnicodeInput(char ch, bool up)
        {
            var input = new INPUT();
            input.Type = INPUT_KEYBOARD;
            input.U.Keyboard = new KEYBDINPUT
            {
                Vk = 0,
                Scan = ch,
                Flags = KEYEVENTF_UNICODE | (up ? KEYEVENTF_KEYUP : 0)
            };
            return input;
        }

        private static double Number(Dictionary<string, object> command, string key)
        {
            object value;
            return command.TryGetValue(key, out value) ? Convert.ToDouble(value) : 0;
        }

        private static string Text(Dictionary<string, object> command, string key, string fallback)
        {
            object value;
            return command.TryGetValue(key, out value) ? Convert.ToString(value) : fallback;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct POINT
        {
            public int X;
            public int Y;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct INPUT
        {
            public uint Type;
            public INPUTUNION U;
        }

        [StructLayout(LayoutKind.Explicit)]
        private struct INPUTUNION
        {
            [FieldOffset(0)]
            public MOUSEINPUT Mouse;

            [FieldOffset(0)]
            public KEYBDINPUT Keyboard;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct MOUSEINPUT
        {
            public int Dx;
            public int Dy;
            public int MouseData;
            public uint Flags;
            public uint Time;
            public IntPtr ExtraInfo;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct KEYBDINPUT
        {
            public ushort Vk;
            public ushort Scan;
            public uint Flags;
            public uint Time;
            public IntPtr ExtraInfo;
        }
    }
}
