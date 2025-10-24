import React, { useState, useEffect } from "react";
import "./DeviceVisualizer.css";

const API_URL = "http://localhost:5000";

function DeviceVisualizer({ devices, socket }) {
    const [selectedDevice, setSelectedDevice] = useState(null);
    const [deviceData, setDeviceData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [searchTerm, setSearchTerm] = useState("");
    const [filteredDevices, setFilteredDevices] = useState([]);

    useEffect(() => {
        if (devices && devices.length > 0) {
            const filtered = devices.filter((d) =>
                d.device_id.toString().includes(searchTerm)
            );
            setFilteredDevices(filtered);

            if (!selectedDevice && filtered.length > 0) {
                setSelectedDevice(filtered[0].device_id);
            }
        }
    }, [devices, searchTerm]);

    useEffect(() => {
        if (selectedDevice) {
            loadDeviceData(selectedDevice);
        }
    }, [selectedDevice]);

    const loadDeviceData = async (deviceId) => {
        setLoading(true);
        try {
            const response = await fetch(
                `${API_URL}/api/devices/${deviceId}/data`
            );
            const data = await response.json();
            setDeviceData(data);
        } catch (error) {
            console.error("Error loading device data:", error);
        } finally {
            setLoading(false);
        }
    };

    const getDeviceStats = (data) => {
        if (!data || !data.rows) return {};

        const rows = data.rows;
        const columns = data.columns || [];

        return {
            total_rows: rows.length,
            total_columns: columns.length,
            date_range:
                rows.length > 0
                    ? `${rows[0][0]} to ${rows[rows.length - 1][0]}`
                    : "N/A",
        };
    };

    return (
        <div className="device-visualizer">
            <div className="device-header">
                <h2>💻 Device Data Visualization (Most Important!)</h2>
                <p>Select a device to view its data and metrics</p>
            </div>

            <div className="device-layout">
                <div className="device-sidebar">
                    <div className="device-search">
                        <input
                            type="text"
                            placeholder="Search device ID..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                        />
                    </div>

                    <div className="device-list">
                        <h3>📱 Available Devices ({filteredDevices.length})</h3>
                        <div className="devices-scroll">
                            {filteredDevices.slice(0, 100).map((device) => (
                                <div
                                    key={device.device_id}
                                    className={`device-item ${
                                        selectedDevice === device.device_id
                                            ? "selected"
                                            : ""
                                    }`}
                                    onClick={() =>
                                        setSelectedDevice(device.device_id)
                                    }
                                >
                                    <span className="device-icon">💾</span>
                                    <span className="device-name">
                                        Device {device.device_id}
                                    </span>
                                    <span className="device-indicator">
                                        {device.status === "trained" && "✅"}
                                        {device.status === "training" && "⏳"}
                                        {device.status === "idle" && "⏸️"}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                <div className="device-main">
                    {selectedDevice && (
                        <>
                            <div className="device-info-panel">
                                <h3>Device {selectedDevice}</h3>
                                {loading && (
                                    <div className="loading">
                                        Loading device data...
                                    </div>
                                )}

                                {deviceData && (
                                    <>
                                        <div className="device-stats">
                                            <div className="stat">
                                                <span className="label">
                                                    Total Rows
                                                </span>
                                                <span className="value">
                                                    {
                                                        getDeviceStats(
                                                            deviceData
                                                        ).total_rows
                                                    }
                                                </span>
                                            </div>
                                            <div className="stat">
                                                <span className="label">
                                                    Columns
                                                </span>
                                                <span className="value">
                                                    {
                                                        getDeviceStats(
                                                            deviceData
                                                        ).total_columns
                                                    }
                                                </span>
                                            </div>
                                            <div className="stat">
                                                <span className="label">
                                                    Date Range
                                                </span>
                                                <span className="value">
                                                    {
                                                        getDeviceStats(
                                                            deviceData
                                                        ).date_range
                                                    }
                                                </span>
                                            </div>
                                        </div>

                                        <div className="data-table-container">
                                            <h4>
                                                📊 Data Preview (First 20 rows)
                                            </h4>
                                            <div className="data-table">
                                                <table>
                                                    <thead>
                                                        <tr>
                                                            {deviceData.columns &&
                                                                deviceData.columns.map(
                                                                    (
                                                                        col,
                                                                        idx
                                                                    ) => (
                                                                        <th
                                                                            key={
                                                                                idx
                                                                            }
                                                                        >
                                                                            {
                                                                                col
                                                                            }
                                                                        </th>
                                                                    )
                                                                )}
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {deviceData.rows &&
                                                            deviceData.rows
                                                                .slice(0, 20)
                                                                .map(
                                                                    (
                                                                        row,
                                                                        idx
                                                                    ) => (
                                                                        <tr
                                                                            key={
                                                                                idx
                                                                            }
                                                                        >
                                                                            {row.map(
                                                                                (
                                                                                    cell,
                                                                                    cidx
                                                                                ) => (
                                                                                    <td
                                                                                        key={
                                                                                            cidx
                                                                                        }
                                                                                    >
                                                                                        {typeof cell ===
                                                                                        "number"
                                                                                            ? cell.toFixed(
                                                                                                  2
                                                                                              )
                                                                                            : cell}
                                                                                    </td>
                                                                                )
                                                                            )}
                                                                        </tr>
                                                                    )
                                                                )}
                                                    </tbody>
                                                </table>
                                            </div>
                                            {deviceData.rows &&
                                                deviceData.rows.length > 20 && (
                                                    <div className="more-rows">
                                                        ... and{" "}
                                                        {deviceData.rows
                                                            .length - 20}{" "}
                                                        more rows
                                                    </div>
                                                )}
                                        </div>

                                        <div className="column-info">
                                            <h4>📋 Column Information</h4>
                                            <div className="columns-grid">
                                                {deviceData.columns &&
                                                    deviceData.columns.map(
                                                        (col, idx) => (
                                                            <div
                                                                key={idx}
                                                                className="column-badge"
                                                            >
                                                                {col}
                                                            </div>
                                                        )
                                                    )}
                                            </div>
                                        </div>
                                    </>
                                )}
                            </div>
                        </>
                    )}

                    {!selectedDevice && (
                        <div className="no-device-selected">
                            <p>
                                Select a device from the list to view its data
                            </p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

export default DeviceVisualizer;
