; Inno Setup script for the local Secure Messenger desktop installer.
; Build after PyInstaller has produced the three onedir bundles in dist/.

#define AppName "Secure Messenger"
#define AppVersion "1.0.0"
#define AppPublisher "Secure Messenger"
#define AppExeClient "SecureMessengerClient.exe"
#define AppExeServer "SecureMessengerServer.exe"
#define AppExeCertificate "SecureMessengerCertificate.exe"

[Setup]
AppId={{D70C05AD-3038-4B6E-BDEE-19391DB518F5}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName=D:\SecureMessenger
DisableProgramGroupPage=yes
OutputDir=..\installer-output
OutputBaseFilename=SecureMessenger-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayName={#AppName}

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "..\dist\SecureMessengerClient\*"; DestDir: "{app}\client"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\SecureMessengerServer\*"; DestDir: "{app}\server"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\SecureMessengerCertificate\*"; DestDir: "{app}\tools"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\config.ini"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "..\runtime\server-cert.pem"; DestDir: "{app}\runtime"; Flags: onlyifdoesntexist
Source: "..\runtime\server-key.pem"; DestDir: "{app}\runtime"; Flags: onlyifdoesntexist
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}\启动服务端"; Filename: "{app}\server\{#AppExeServer}"; WorkingDir: "{app}\server"
Name: "{autoprograms}\{#AppName}\启动客户端"; Filename: "{app}\client\{#AppExeClient}"; WorkingDir: "{app}\client"
Name: "{autoprograms}\{#AppName}\重新生成 TLS 证书"; Filename: "{app}\tools\{#AppExeCertificate}"; WorkingDir: "{app}\tools"
Name: "{autodesktop}\Secure Messenger"; Filename: "{app}\client\{#AppExeClient}"; WorkingDir: "{app}\client"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建客户端桌面快捷方式"; GroupDescription: "附加图标："

[Run]
Filename: "{app}\README.md"; Description: "查看安装与启动说明"; Flags: postinstall shellexec skipifsilent
