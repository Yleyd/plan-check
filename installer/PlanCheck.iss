; Plan check 安装脚本（Inno Setup 6）
; 编译：ISCC.exe PlanCheck.iss

#define AppName "Plan check"
#define AppExe "PlanCheck.exe"
#define AppVersion "1.0.3"
#define AppPublisher "Plan check"
#define AppId "{{8F3C1A20-6D42-4E71-9B58-2C7A5E0D91B4}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\PlanCheck
DefaultGroupName={#AppName}
AllowNoIcons=yes
; 允许用户自选安装目录
DisableDirPage=no
DirExistsWarning=auto
OutputDir=..\release
OutputBaseFilename=PlanCheck-{#AppVersion}-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} {#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
ShowLanguageDialog=no
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} 安装程序
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}

[Languages]
Name: "chinese"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式(&D)"; GroupDescription: "附加快捷方式："
Name: "startmenu"; Description: "创建开始菜单快捷方式(&S)"; GroupDescription: "附加快捷方式："

[Files]
Source: "..\dist\PlanCheck.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\NOTICE.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\assets\default\*.jpg"; DestDir: "{app}\assets\default"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startmenu
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"; Tasks: startmenu
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即运行 {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 只清理程序自身目录里的运行时缓存；用户数据默认保留（卸载时会询问）
Type: filesandordirs; Name: "{app}\data\logs"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
  Ask: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    DataDir := ExpandConstant('{app}\data');
    if DirExists(DataDir) then
    begin
      // 静默卸载不弹窗，一律保留数据，避免误删
      if UninstallSilent then
        Exit;
      Ask := MsgBox('是否保留你的学习计划与打卡记录？' + #13#10 + #13#10 +
                    '选择「是」保留（下次安装还能接着用），选择「否」则一并删除。' + #13#10 +
                    '数据位置：' + DataDir,
                    mbConfirmation, MB_YESNO or MB_DEFBUTTON1);
      if Ask = IDNO then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
