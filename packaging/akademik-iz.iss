; Akademik İz kurulum dosyası (Inno Setup 6).
;
;   1) .venv\Scripts\python -m PyInstaller packaging\akademik-iz.spec --noconfirm --distpath dist --workpath build
;   2) "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" packaging\akademik-iz.iss
;
; Çıktı: dist\AkademikIz-Kurulum.exe. Kullanıcı başına kurulur (yönetici izni istemez): uygulama ayarları, anahtarlar
; ve indirilen veri kurulum klasöründe tutulduğu için klasörün yazılabilir olması gerekir.

#define AppName "Akademik İz"
#define AppVersion "1.0.0"
#define AppExe "AkademikIz.exe"

[Setup]
AppId={{6B2E7C1A-3F4D-4E8B-9A51-2C7D8E9F0A11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Akademik İz
AppComments=Akademisyen, üniversite ve firma keşif platformu
DefaultDirName={localappdata}\Programs\AkademikIz
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=AkademikIz-Kurulum
; Kurulum dosyasının simgesi: logo açık bir kurulum kutusunun içinde (packaging/make_icon.py).
SetupIconFile=akademik-iz-setup.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardImageFile=wizard-large.bmp
WizardSmallImageFile=wizard-small.bmp
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaüstüne kısayol oluştur"; GroupDescription: "Kısayollar:"

[Files]
Source: "..\dist\AkademikIz\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} kaldır"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{#AppName} uygulamasını şimdi başlat"; Flags: nowait postinstall skipifsilent

[InstallDelete]
; İlk derleme önbelleği yanlış kodlamayla yazıyordu: üzerine kurulurken eski önbellek silinir.
Type: filesandordirs; Name: "{app}\_internal\data"

[UninstallDelete]
; Uygulamanın çalışırken oluşturduğu veri, ayar ve önbellek dosyaları da kaldırılır.
Type: filesandordirs; Name: "{app}\_internal\data"
Type: filesandordirs; Name: "{app}\_internal\.cache"
Type: files; Name: "{app}\_internal\.ai-settings.json"
Type: files; Name: "{app}\_internal\.app-settings.json"
