import React, { useState, useEffect } from "react";
import "./NotebookViewer.css";

const API_URL = "http://localhost:5000";

function NotebookViewer({ socket }) {
    const [notebookContent, setNotebookContent] = useState(null);
    const [isRunning, setIsRunning] = useState(false);
    const [output, setOutput] = useState([]);
    const [errors, setErrors] = useState([]);
    const [status, setStatus] = useState("idle");

    useEffect(() => {
        loadNotebook();
        if (socket) {
            socket.on("notebook_output", (data) => {
                setOutput((prev) => [...prev, data]);
            });
            socket.on("notebook_error", (data) => {
                setErrors((prev) => [...prev, data]);
            });
            socket.on("notebook_complete", (data) => {
                setStatus("complete");
                setIsRunning(false);
            });
        }
    }, [socket]);

    const loadNotebook = async () => {
        try {
            const response = await fetch(`${API_URL}/api/notebook/content`);
            const data = await response.json();
            setNotebookContent(data);
        } catch (error) {
            console.error("Error loading notebook:", error);
        }
    };

    const runNotebook = async () => {
        setIsRunning(true);
        setOutput([]);
        setErrors([]);
        setStatus("running");

        try {
            const response = await fetch(`${API_URL}/api/notebook/execute`, {
                method: "POST",
            });

            if (!response.ok) {
                const errorData = await response.json();
                setErrors([errorData.error || "Failed to run notebook"]);
                setStatus("error");
            }
        } catch (error) {
            setErrors([error.message]);
            setStatus("error");
        } finally {
            setIsRunning(false);
        }
    };

    return (
        <div className="notebook-viewer">
            <div className="notebook-header">
                <h2>📓 Data Preprocessing Notebook</h2>
                <button
                    className="btn-run"
                    onClick={runNotebook}
                    disabled={isRunning}
                >
                    {isRunning ? "⏳ Running..." : "▶️ Run Notebook"}
                </button>
            </div>

            <div className="notebook-status">
                <div className={`status-indicator ${status}`}>
                    {status === "running" && "🔄 Running"}
                    {status === "complete" && "✅ Complete"}
                    {status === "error" && "❌ Error"}
                    {status === "idle" && "⏸️ Idle"}
                </div>
            </div>

            <div className="notebook-container">
                <div className="notebook-content">
                    {notebookContent && notebookContent.cells && (
                        <div className="cells">
                            {notebookContent.cells.map((cell, idx) => (
                                <div
                                    key={idx}
                                    className={`cell ${cell.cell_type}`}
                                >
                                    <div className="cell-header">
                                        <span className="cell-type">
                                            {cell.cell_type}
                                        </span>
                                        <span className="cell-number">
                                            [{idx + 1}]
                                        </span>
                                    </div>
                                    {cell.cell_type === "code" && (
                                        <pre className="cell-code">
                                            <code>{cell.source}</code>
                                        </pre>
                                    )}
                                    {cell.cell_type === "markdown" && (
                                        <div className="cell-markdown">
                                            {cell.source}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                <div className="notebook-output">
                    <div className="output-section">
                        <h3>📤 Output</h3>
                        <div className="output-logs">
                            {output.length > 0 ? (
                                output.map((log, idx) => (
                                    <div key={idx} className="output-line">
                                        {log}
                                    </div>
                                ))
                            ) : (
                                <div className="empty-state">
                                    Run notebook to see output...
                                </div>
                            )}
                        </div>
                    </div>

                    <div className="output-section errors">
                        <h3>❌ Errors</h3>
                        <div className="error-logs">
                            {errors.length > 0 ? (
                                errors.map((error, idx) => (
                                    <div key={idx} className="error-line">
                                        {error}
                                    </div>
                                ))
                            ) : (
                                <div className="empty-state">No errors</div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default NotebookViewer;
