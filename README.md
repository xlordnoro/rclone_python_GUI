# rclone_python_GUI
A Basic rclone GUI made in python with pyqt6

# Prep Work
**Requires rclone along with any modern version of Python, and it must be in your system path to run anywhere. Linux will add it to the system path by default, but Windows users will need to add it manually to use it globally.**

I'm running the latest stable build of Python, which is `3.14.4` on cachyos, but any modern version will work for this program.

# Linux Installation
Rclone can be downloaded via your package manager.

- `sudo pacman -S rclone`
- `sudo apt install rclone`
- `sudo dnf install rclone`

Run `rclone config` in the terminal to enter the rclone setup and add your remote by following the prompts using the credentials for your account(s).

Depending on your flavor of Linux, you may have to create a virtual environment to install `PyQt6`. 

Arch Linux uses an externally managed installation, so I have to use the virtual environment to install dependencies globally, or I'll get an error when trying to install libraries via pip. Some will work without the environment, but some will flat-out fail to run otherwise. By all means, if someone knows a different method, feel free to let me know so I can update the guide.

- Run `python -m venv myenv` to create the virtual environment in the current working directory. You can change the myenv to anything you want, but this will work for testing or if you don't care about the name.
- Next, run `source myenv/bin/activate` to enter the virtual environment. If you changed the name in the previous command, swap myenv for the name you provided, or it will not work!
- Run `pip install PyQt6` to download the GUI library needed to run the script, or you'll get import errors when attempting to run the Python script.
With `PyQt6` installed now, you can run `python3 rclone_GUI.pyw`. You need to run the script in the virtual environment since `PyQt6` is only available in the environment and trying to run it outside will result in an import error.
- Run `deactivate` to exit the virtual environment.

# Windows Installation
Download rclone from the following link and select the 64-bit zip since it's a portable application: <a href="https://rclone.org/downloads/" alt="rclone">Rclone</a>

Once it's downloaded, extract the contents of the folder somewhere on your pc that you'll remember. Make sure it's somewhere you won't move, or it'll break the next steps if the location is changed! It can be fixed by changing the location again, but it's best to set it and forget it to avoid future headaches. 

Once it's been extracted, you'll need to add the rclone folder to your system path. Doing that will allow you and the script to call rclone anywhere, even when you're not in the same folder as rclone.

**Go to the location of your rclone folder and copy the folder path to your clipboard. You can copy the folder path by clicking the path URL in File Explorer. We'll need that shortly to add it to the system path.**

Search for `changing environment variable` in Windows search, and it will be the first result. Click on it to open a new window, which will show a button in the bottom-left labelled `environment variables.`

Your screen should look like this now. You might need to scroll down a bit to see it, but once you find `PATH` under system variables, double-click it to open another window, and we'll be able to add the rclone folder to our system path.

Click on `new` in the top-right and paste the folder path to your rclone folder, and hit okay once you're done.

To test that everything is working correctly, search for `Windows Terminal` on Windows 11, or you can use `cmd` or `powershell` on Windows 10.

Type `rclone` and you should see a bunch of text output to the console. It'll likely say that you need to supply arguments or something along those lines, but that's okay since we're just testing the path!

If you get an error stating `rclone is not an internal or external program`, then your rclone folder path is either incorrect, or if you had a terminal window active, you'll need to close it since the system path is only refreshed when the program is reopened.

If everything is running okay, type `rclone config` to set up the remote for your account(s). Once you finish entering your remote name, provider, and account details, it will ask some additional questions. Just type `n` or press enter with the defaults if you're unsure what they mean. I'm only familiar with B2, aka Backblaze. So bear that in mind.

Once you're back to the initial setup screen, type `q` to quit the setup process, and we can finally move on to the rclone GUI stuff.

Unlike Linux, Windows doesn't come with Python pre-installed, so you'll need to grab the latest stable build from their site. <a href="https://www.python.org/downloads/windows/" alt="python">Python</a>

Make sure to select `add to system path` on the first page of the installer, or you won't be able to call Python or pip globally as we did with rclone.

It will take a bit to install since it needs to download a bunch of libraries to function properly, but once the installation is complete, you're ready to install `PyQt6` on your system.

Run `pip install PyQt6`, and it will immediately start downloading the library to your system. It's a few hundred mb so if your internet is slow, just be patient and let it do its thing.

Once `PyQt6` is installed, you can run `rclone_GUI.pyw` without triggering any errors. You can either double-click it in file explorer or run it as a command `python rclone_GUI.pyw` in the terminal, and you should see a terminal window pop up with rclone. Close the rclone window. I'm not 100% sure why it only happens in Windows since Linux doesn't do that (might be a subprocess difference between the OS's), and you should see the GUI like this.

By design, it will auto-populate all rclone remotes detected on your system into a dropdown list. I only have one Rclone remote, so it's the only one that will show up in the dropdown menu.

<img width="1205" height="735" alt="cyberdunk_clone_blur" src="https://github.com/user-attachments/assets/5f84f707-f373-4690-920c-69eff1405b1b" />
