# rclone_python_GUI
A Basic rclone GUI made in python with pyqt6

# Prep Work
Requires rclone along with any modern version of Python, and it must be in your system path to run anywhere. Linux will add it to the system path by default, but Windows users will need to add it manually to use it globally.

I'm running the latest stable build of Python, which is `3.14.4` on cachyos, but any modern version will work for this program.

# Linux Installation
Rclone can be downloaded via your package manager. Since I'm running cachyos, which is based on Arch Linux, I'll use pacman. Apt will be used for Ubuntu/Debian-based distros, and dnf for Fedora-based distros.

- `sudo pacman -S rclone`
- `sudo apt install rclone`
- `sudo dnf install rclone`

Run `rclone config` in the terminal to enter the rclone setup and add your remote by following the prompts using the credentials for your account(s).

Depending on your flavor of Linux, you may have to create a virtual environment to install `PyQt6`. 

Arch Linux uses an externally managed installation, so I have to use the virtual environment to install dependencies globally, or I'll get an error when trying to install libraries via pip. Some will work without the environment, but some will flat out not work to my knowledge. By all means, if someone knows a different method, feel free to let me know so I can update the guide.

- Run `python -m venv myenv` to create the virtual environment in the current working directory. You can change the myenv to anything you want, but this will work for testing or if you don't care about the name.
- Next, run `source myenv/bin/activate` to enter the virtual environment. If you changed the name in the previous command, swap myenv for the name you provided, or it will not work.
- Run `pip install PyQt6` to download the GUI library needed to run the script, or you'll get import errors when attempting to run it.
With `PyQt6` installed now, you can run `python3 rclone_GUI.pyw`. You need to run the script in the virtual environment since `PyQt6` is only available in the environment and trying to run it outside will result in an import error.
- Run `deactivate` to exit the virtual environment.
