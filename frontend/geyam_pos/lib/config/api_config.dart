class ApiConfig {
  // Phone testing on LAN — use the laptop's Wi-Fi IP, not 127.0.0.1
  // (which would point at the phone itself). Switch to api.geyam.com
  // once the Cloudflare Tunnel is up.
  static const String baseUrl = 'http://172.19.180.37:8000';
}
