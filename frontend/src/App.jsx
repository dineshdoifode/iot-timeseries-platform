import { useEffect, useState } from 'react';

const API_BASE = '/api/v1';

function App() {
  const [devices, setDevices] = useState([]);
  const [stats, setStats] = useState(null);
  const [token, setToken] = useState('');
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('ChangeMe123!');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) return;
    fetchDevices();
    fetchStats();
  }, [token]);

  async function login() {
    setError('');
    try {
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (!response.ok) {
        throw new Error('Login failed');
      }
      const data = await response.json();
      setToken(data.access_token);
    } catch (err) {
      setError(err.message);
    }
  }

  async function fetchDevices() {
    const response = await fetch(`${API_BASE}/devices`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await response.json();
    setDevices(data);
  }

  async function fetchStats() {
    const response = await fetch(`${API_BASE}/stats/fleet`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await response.json();
    setStats(data);
  }

  return (
    <div className="app-container">
      <header>
        <h1>IoT Time-Series Platform</h1>
        <p>Device inventory, telemetry overview, and alarm monitoring.</p>
      </header>

      {!token ? (
        <section className="card login-card">
          <h2>Sign in</h2>
          {error && <div className="error">{error}</div>}
          <label>Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} />
          <label>Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button onClick={login}>Login</button>
        </section>
      ) : (
        <>
          <section className="card stats-card">
            <h2>Fleet statistics</h2>
            {stats ? (
              <div className="stats-grid">
                <div><strong>Total devices</strong><span>{stats.total_devices}</span></div>
                <div><strong>Active devices</strong><span>{stats.active_devices}</span></div>
                <div><strong>Online devices</strong><span>{stats.online_devices}</span></div>
                <div><strong>Active alarms</strong><span>{stats.active_alarms}</span></div>
                <div><strong>Telemetry last hour</strong><span>{stats.telemetry_points_last_hour}</span></div>
              </div>
            ) : (
              <p>Loading statistics...</p>
            )}
          </section>

          <section className="card devices-card">
            <h2>Devices</h2>
            <table>
              <thead>
                <tr>
                  <th>Device ID</th>
                  <th>Type</th>
                  <th>Group</th>
                  <th>Active</th>
                </tr>
              </thead>
              <tbody>
                {devices.length ? (
                  devices.map((device) => (
                    <tr key={device.device_id}>
                      <td>{device.device_id}</td>
                      <td>{device.device_type || '-'}</td>
                      <td>{device.device_group || '-'}</td>
                      <td>{device.is_active ? 'Yes' : 'No'}</td>
                    </tr>
                  ))
                ) : (
                  <tr><td colSpan="4">No devices found</td></tr>
                )}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}

export default App;
