# Octoslack #
An OctoPrint plugin for monitoring your printer and prints via Slack, Mattermost, Pushbullet, Pushover, Rocket.Chat, Discord, Element/Matrix, or Microsoft Teams

# Features #
 - Support for Slack, Mattermost, Pushbullet, Pushover, Rocket.Chat, Discord, Matrix based platforms (e.g. Element), & Microsoft Teams
 - Monitor both print status as well as printer connectivity status
 - Respond to Slack commands to check print status or cancel/pause/resume a print
     - Each command can be individually enabled/disbaled or flagged as restricted which limits the command(s) to specific users
     - Requires use of the Slack App Bot Token
 - Customizable messages
     - Slack and Mattermost support for a fallback message (e.g. mobile notification)
     - Pushover support for event specific sound and priority settings
 - Support for posting to one more channels as well as event level channel overrides
 - Support for inclusion of RasPi temperature, bed temperature, nozzle temperates, nozzle height, and device IP(s)
 - Support for local system command execution
 - Slack bot name/icon/emoji customizations
     - Requires use of the Slack App Bot Token
 - Optional inclusion of printer snapshot images with each message
     - Support for snapshot hosting via Amazon S3, Minio, Imgur (with album support), Slack attachments, Pushover, Pushbullet, Rocket.Chat, Discord, or Matrix
     - Slack attachments requires use of the Slack App Bot Token
 - Optional upload of rendered timelapse video to configured hosting service
     - Currently excludes Imgur, Pushover, Rocket.Chat, Discord, & Matrix
 - Support for additional snapshot images from IP cameras
 
 # Supported Events #
 - Print started
 - Print failed
 - Print cancelling
 - Print cancelled
 - Print paused
 - Print resumed
 - Print finished
 - Print progress (% complete)
 - Print progress (time interval)
 - Print progress (Z height change)
 - G-code sent to the printer
 - G-code received from the printer (including filament runout messages)
 - Timelapse render started
 - Timelapse render finished (including Octolapse timelapses)
 - Timelapse render failed
 - File analysis started
 - File analysis finished
 - OctoPrint error
 - OctoPrint started
 - OctoPrint stopped
 - Printer connecting
 - Printer connected
 - Printer disconnecting
 - Printer disconnected

# Manual installation steps #

    pip install "https://github.com/fraschetti/Octoslack/archive/master.zip"

# Slack/Mattermost Examples #

> ### Print Started ###
> ![Print started example](/screenshots/Octoslack-PrintStarted.png?raw=true)
> ###### Left = Slack  /  Right = Mattermost ######

> ### Print Progress ###
> ![Print progress example](/screenshots/Octoslack-PrintProgress.png?raw=true)
> ###### Left = Slack  /  Right = Mattermost ######

> ### Print Finished ###
> ![Print finished example](/screenshots/Octoslack-PrintFinished.png?raw=true)
> ###### Left = Slack  /  Right = Mattermost ######

# Pushbullet Example #

> ### Print Started ###
> ![Pushbullet - Print started example](/screenshots/Octoslack-Pushbullet-PrintStarted.png?raw=true)

# Pushover Example #

> ### Print Started ###
> ![Pushover - Print started example](/screenshots/Octoslack-Pushover-PrintStarted.png?raw=true)

# Rocket.Chat Example #

> ### Print Started ###
> ![Rocket.Chat - Print started example](/screenshots/Octoslack-RocketChat-PrintStarted.png?raw=true)

# Matrix/Element Example #

> ### Print Started ###
> ![Matrix/Element - Print started example](/screenshots/Octoslack-Matrix-PrintStarted.png?raw=true)

# G-code event & System command Example #

> ### G-code event & System command ###
> ![G-code event & System command Example](/screenshots/Octoslack-GcodeEventCommand.png?raw=true)
