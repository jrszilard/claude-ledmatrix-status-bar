# Claude LED Matrix Status Bar

A Raspberry Pi-powered LED matrix display that shows your Claude subscription usage and Anthropic API spend in real time.

Your personal machine scrapes Claude Code's `/usage` data and pushes it to the Pi over WiFi. The Pi also pulls API usage directly from the Anthropic Admin API. The display cycles through each metric with color-coded progress bars and fade transitions.

## What It Shows

- **Session usage** (red) — current 5-hour session percentage and reset time
- **Weekly usage — all models** (yellow) — weekly percentage across all models
- **Weekly usage — Sonnet only** (green) — weekly Sonnet-specific percentage
- **Extra usage** (blue) — dollar spend against your extra usage limit
- **API usage** (purple) — total API spend and token count across your projects

Each metric displays for a few seconds with a progress bar, then fades to the next.

## Hardware

- Raspberry Pi 3B (or newer)
- HUB75 RGB LED matrix panels (tested with Adafruit 16x32 and 32x64 panels)
- 5V power supply for the panels (separate from the Pi — panels draw significant current)
- GPIO wiring from Pi to first panel's HUB75 input, panels daisy-chained via ribbon cables

The Pi drives the panels using the [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) library via direct GPIO.

## Architecture

```
Your Machine                          Raspberry Pi
+------------------+                  +---------------------------+
| Claude Code CLI  |   HTTP POST     | HTTP Receiver (port 8765) |
| /usage scraping  | ----WiFi------> | Updates subscription data |
| (cron, every 5m) |                  |                           |
+------------------+                  | API Collector (thread)    |
                                      | Polls Anthropic Admin API |
                                      |                           |
                                      | LED Renderer (main thread)|
                                      | Drives HUB75 panels       |
                                      +---------------------------+
```

## Pi Setup

### 1. Flash Raspberry Pi OS

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) to flash **Raspberry Pi OS Lite** to your SD card. In the imager settings, pre-configure:
- WiFi credentials
- SSH enabled
- Username and password

### 2. Disable audio (conflicts with LED driver)

```bash
sudo bash -c 'echo dtparam=audio=off >> /boot/firmware/config.txt'
sudo bash -c 'echo blacklist snd_bcm2835 > /etc/modprobe.d/alsa-blacklist.conf'
```

Optionally reserve a CPU core for the LED driver:
```bash
sudo bash -c 'sed -i "s/$/ isolcpus=3/" /boot/firmware/cmdline.txt'
```

Reboot after these changes.

### 3. Install dependencies

```bash
sudo apt-get update
sudo apt-get install -y git python3-pip python3-dev python3-venv build-essential cython3
```

### 4. Clone and build

```bash
cd ~
git clone https://github.com/jrszilard/claude-ledmatrix-status-bar.git
cd claude-ledmatrix-status-bar

# Create Python venv and install deps
python3 -m venv venv
source venv/bin/activate
pip install pyyaml requests

# Build rpi-rgb-led-matrix
cd ~
git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
cd rpi-rgb-led-matrix
make -C lib
cd ~/claude-ledmatrix-status-bar
source venv/bin/activate
pip install ~/rpi-rgb-led-matrix

# Link fonts
ln -sfn ~/rpi-rgb-led-matrix/fonts ~/claude-ledmatrix-status-bar/fonts
```

### 5. Configure

```bash
cd ~/claude-ledmatrix-status-bar
cp config.example.yaml config.yaml
```

Edit `config.yaml`:

```yaml
display:
  panels: 3              # number of chained panels
  rows: 16               # panel height (16 or 32)
  cols_per_panel: 32      # panel width (32 or 64)
  gpio_mapping: regular   # GPIO wiring scheme (see Troubleshooting)
  gpio_slowdown: 3        # GPIO timing (2-4, tune for your Pi)
  brightness: 35          # 0-100
  pwm_bits: 4             # color depth (lower = less flicker, 4-11)
  scan_mode: 1            # 0=interlaced, 1=progressive
  ticker_cycle_seconds: 4  # seconds per metric
  ticker_fade_frames: 15   # fade transition speed

polling:
  api_interval_seconds: 300  # how often to fetch API usage

receiver:
  port: 8765
  token: "your-shared-secret-here"  # must match client config

anthropic:
  admin_api_key: "sk-ant-admin-your-key"  # from console.anthropic.com
  api_projects:
    - name: "my-project"
      api_key_id: "apikey_01EXAMPLE"  # API key ID, not the key itself
```

To skip API tracking, set `api_interval_seconds` to a very high number and leave `api_projects` empty.

### 6. Test

```bash
# Dry-run mode (no LED hardware needed)
source venv/bin/activate
python3 -m src.main --dry-run -c config.yaml

# Real LED output (requires root for GPIO)
sudo venv/bin/python3 -m src.main -c config.yaml
```

Push test data from another machine:
```bash
curl -X POST http://YOUR_PI_IP:8765/usage \
  -H "Authorization: Bearer your-shared-secret-here" \
  -H "Content-Type: application/json" \
  -d '{"session_pct":42,"session_reset":"9pm","week_all_pct":55,"week_all_reset":"Apr 12","week_sonnet_pct":20,"week_sonnet_reset":"Apr 11","extra_spent":15.5,"extra_limit":79.0}'
```

### 7. Install as a service

```bash
sudo cp claude-status-bar.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable claude-status-bar
sudo systemctl start claude-status-bar
```

Check status:
```bash
sudo systemctl status claude-status-bar
sudo journalctl -u claude-status-bar -f
```

## Client Setup (Your Personal Machine)

The client script runs on any machine with Claude Code installed. It scrapes the `/usage` TUI output and pushes it to the Pi.

### Requirements

- Python 3.7+
- `tmux` and `claude` CLI installed
- `requests` library (`pip install requests`)
- Network access to the Pi

### One-shot test

```bash
python client/push_usage.py --host YOUR_PI_IP --token your-shared-secret-here
```

### Cron job (recommended)

Run every 5 minutes:
```bash
crontab -e
```
Add:
```
*/5 * * * * /path/to/venv/bin/python /path/to/client/push_usage.py --host YOUR_PI_IP --token your-shared-secret-here >> /tmp/push_usage.log 2>&1
```

### Continuous mode

```bash
python client/push_usage.py --host YOUR_PI_IP --token your-shared-secret-here --loop --interval 300
```

## Configuration Reference

### Display options

| Option | Default | Description |
|--------|---------|-------------|
| `panels` | 3 | Number of daisy-chained panels |
| `rows` | 16 | Panel height in pixels (16 or 32) |
| `cols_per_panel` | 32 | Panel width in pixels (32 or 64) |
| `gpio_mapping` | `regular` | GPIO wiring scheme (`regular`, `adafruit-hat`, `adafruit-hat-pwm`, `classic`) |
| `gpio_slowdown` | 3 | GPIO timing factor (higher = slower, more stable) |
| `brightness` | 35 | LED brightness 0-100 |
| `pwm_bits` | 4 | Color depth bits (4-11, lower = less flicker) |
| `pwm_lsb_nanoseconds` | 130 | PWM timing in nanoseconds |
| `scan_mode` | 1 | Scan pattern (0=interlaced, 1=progressive) |
| `ticker_cycle_seconds` | 4 | Seconds between metric transitions |
| `ticker_fade_frames` | 15 | Frames for fade transition |

### Receiver options

| Option | Default | Description |
|--------|---------|-------------|
| `port` | 8765 | HTTP server port |
| `token` | (required) | Shared secret for authentication |

### Anthropic API options

| Option | Description |
|--------|-------------|
| `admin_api_key` | Admin API key from console.anthropic.com (starts with `sk-ant-admin...`) |
| `api_projects` | List of `{name, api_key_id}` entries to track |

## Troubleshooting

### Display is flickering
- Lower `pwm_bits` (try 4)
- Set `scan_mode: 1` (progressive)
- Tune `gpio_slowdown` (try values 2-4)
- Make sure `isolcpus=3` is in `/boot/firmware/cmdline.txt`
- Disable the sound module (see Pi Setup step 2)

### Display shows garbled output
- Wrong `gpio_mapping` — try `regular`, `adafruit-hat`, or `classic` until one works
- Check ribbon cable connections between Pi GPIO and panel HUB75 input

### Panels flash with Pi powered off
- Normal — HUB75 inputs float when no signal is present. Panels need an active driver signal.

### Push client returns 0% for everything
- The `/usage` TUI needs time to render. The client waits ~20 seconds total. If your machine is slow, increase the sleep times in `client/push_usage.py`.

### "snd_bcm2835" error on startup
- The Pi's audio module conflicts with the LED GPIO driver. Disable it:
  ```bash
  sudo bash -c 'echo dtparam=audio=off >> /boot/firmware/config.txt'
  sudo reboot
  ```

### API usage shows "401 Unauthorized"
- Your admin API key is invalid or not set. Get one from console.anthropic.com under Settings > Admin Keys.
- To skip API tracking, set `api_interval_seconds: 99999` in config.

### Service won't start
- Check logs: `sudo journalctl -u claude-status-bar -f`
- The LED driver requires root. Make sure the service runs as `User=root`.
- Verify the venv path in the service file matches your install location.

## Project Structure

```
claude-ledmatrix-status-bar/
├── config.example.yaml       # Template — copy to config.yaml
├── claude-status-bar.service  # systemd unit file
├── claude-status-bar.env.example
├── install.sh                 # Automated installer
├── requirements.txt
├── src/
│   ├── main.py                # Entry point, thread orchestration
│   ├── config.py              # YAML config loader with env var interpolation
│   ├── collector.py           # Anthropic Admin API usage/cost fetcher
│   ├── receiver.py            # HTTP server for subscription data pushes
│   ├── renderer.py            # LED matrix drawing (metrics + fade cycling)
│   └── layout.py              # Pixel coordinates, colors, formatting helpers
├── client/
│   └── push_usage.py          # Runs on your machine — scrapes /usage, pushes to Pi
└── tests/
    ├── test_config.py
    ├── test_layout.py
    ├── test_collector.py
    ├── test_receiver.py
    ├── test_renderer.py
    └── test_client.py
```

## License

MIT
