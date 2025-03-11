## 1. Unlocking features and install wsl2

### 1.1 use install bat to install wsl2
Open wsl_install.bat as an administrator.

- Right click -> Run as administrator...

You should see: 


![Output from running the above commands successfully.](images/wsl_install.png)

If you cannot run this file successfully, try:

Go to microsoft store and install [ubuntu-22.04](https://apps.microsoft.com/detail/9pn20msr04dw?ocid=webpdpshare)

### 1.2 reboot
Before moving forward, make sure you reboot your computer so that Windows 11 will have WSL2 and virtualization available to it.

## 2. Init wsl2 environment

[wsl2 image](https://drive.google.com/file/d/1OK2Sd2Ylwd1J3cMOLr_SgYnhmDdidtOl/view?usp=sharing)

### import wsl2 environment
```bash
wsl --import ivry path\to\your\wsl\path path\to\backup.tar
```
example:
```bash
wsl --import ivry C:\WSL\Ubuntu C:\User\Downloads\ivry-cli.tar
```

password for wsl2 ivry is ivry
```bash
wsl -d ivry
```


## 3. Get into ivry_cli

check ivry_cli:
```bash
cd /opt/ivry_cli
```
```bash
source venv/bin/activate
```
```bash
ivry_cli
```
