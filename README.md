# Octoslack #
An OctoPrint plugin for monitoring your printer and prints via Slack or Mattermost

# Features #
 - Support for both Slack and Mattermost
 - Monitor both print status as well as printer connectivity status
 - Slack+Mattermost WebHooks and Slack API Token
 - Respond to Slack commands to check print status or cancel/pause/resume a print
     - Requires use of the Slack API Token
 - Customizable messages
 - Support for posting to one more channels as well as event level channel overrides
 - Support for inclusion of RasPi temperature, bed temperature, nozzle temperates, nozzle height, and device IP(s)
 - Custom bot name/icon/emoji
 - Optional inclusion of printer snapshot images with each message
     - Support for snapshot hosting via Amazon S3, Minio, Imgur (with album support), or Slack attachments
     - Slack attachments requires use of the Slack API Token
 - Optional upload of rendered timelapse video to configured hosting service
     - Excluding Imgur which does not support video uploads
 - Support for additional snapshot images from IP cameras
 
 # Supported Events #
 - Print started
 - Print failed
 - Print cancelled
 - Print paused
 - Print resumed
 - Print finished
 - Print progress (% complete)
 - Print progress (time interval)
 - Print progress (Z height change)
 - G-code sent to printer
 - G-code received from printer
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
