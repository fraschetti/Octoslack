# Octoslack #
An OctoPrint plugin for monitoring your printer and prints via Slack or Mattermost

# Features #
 - Support for both Slack and Mattermost
 - Monitor both print status as well as printer connectivity status
 - Slack+Mattermost WebHooks and Slack API Token
 - Respond to Slack commands to check print status or cancel/pause/resume a print
     - Requires use of the Slack API Token
 - Customizable messages
 - Support for inclusion of RasPi temperature, bed temperature, nozzle temperates, and nozzle height
 - Custom bot name/icon/emoji
 - Optional inclusion of printer snapshot images with each message
     - Support for snapshot hosting on either Amazon S3 or Imgur
 - Support for additional snapshot images from IP cameras
 
 # Supported Events #
 - Print started
 - Print failed
 - Print cancelled
 - Print paused
 - Print resumed
 - Print finished
 - Print progress
 - Timelapse render started
 - Timelapse render finished
 - Timelapse render failed
 - OctoPrint error
 - OctoPrint started
 - OctoPrint stopped
 - Printer connecting
 - Printer connected
 - Printer disconnecting
 - Printer disconnected

# Manual installation steps #

    pip install "https://github.com/fraschetti/Octoslack/archive/master.zip"

# Examples #

> ### Print Started ###
> ![Print started example](/screenshots/Octoslack-PrintStarted.png?raw=true)
> ###### Left = Slack  /  Right = Mattermost ######

> ### Print Progress ###
> ![Print progress example](/screenshots/Octoslack-PrintProgress.png?raw=true)
> ###### Left = Slack  /  Right = Mattermost ######

> ### Print Finished ###
> ![Print finished example](/screenshots/Octoslack-PrintFinished.png?raw=true)
> ###### Left = Slack  /  Right = Mattermost ######
