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

### 2.1 install requirements

Install requirements by 

```bash
. install.sh
```

note: if your wsl cannot do apt update, you can open install.sh in notebook and copy paste each steps

(optional)
### 2.2 import wsl2 environment
```bash
wsl --import ivry path\to\your\ivry\path path\to\backup.tar
```
example:
```bash
wsl --import ivry C:\WSL\Ubuntu C:\User\Downloads\Ubuntu22-04.tar
```

password for wsl2 ivry is ivry
```bash
wsl -d ivry -u ivry #to enter the wsl2, make sure you enter wsl2 with user ivry (not root) 
```


## 3. Run webui

Run webui by:
```bash
cd path/to/your/cli
ivry_web
```

