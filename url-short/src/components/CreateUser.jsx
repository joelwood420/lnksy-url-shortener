import React, { useState } from "react";
import "./Create_User.css";

function Create_User({ onClose, onLoginSuccess }) {
    const [isLogin, setIsLogin] = useState(true);
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (event) => {
        event.preventDefault();
        setError("");
        setLoading(true);

        if (!email || !password) {
            setError("Please fill in all fields");
            setLoading(false);
            return;
        }

        if (!isLogin && password !== confirmPassword) {
            setError("Passwords do not match");
            setLoading(false);
            return;
        }

        const endpoint = isLogin ? "/login" : "/register";

        try {
            const response = await fetch(endpoint, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                credentials: "include",
                body: JSON.stringify({ email, password }),
            });

            const data = await response.json();

            if (response.ok) {
                onLoginSuccess(data.email);
                onClose();
            } else {
                setError(data.error || "Something went wrong");
            }
        } catch (err) {
            console.error("Error:", err);
            setError("Failed to connect to server");
        } finally {
            setLoading(false);
        }
    };

    const toggleMode = () => {
        setIsLogin(!isLogin);
        setError("");
        setPassword("");
        setConfirmPassword("");
    };

    return (
        <div className="user-overlay">
            <div className="user-modal">
                <button className="user-close" onClick={onClose}>
                    ×
                </button>
                
                <h2 className="user-title">
                    {isLogin ? "Login" : "Create Account"}
                </h2>
                
                <form onSubmit={handleSubmit} className="user-form">
                    <div className="user-field">
                        <label htmlFor="email">Email</label>
                        <input
                            id="email"
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="Enter your email"
                            required
                        />
                    </div>

                    <div className="user-field">
                        <label htmlFor="password">Password</label>
                        <input
                            id="password"
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="Enter your password"
                            required
                        />
                    </div>

                    {!isLogin && (
                        <div className="user-field">
                            <label htmlFor="confirmPassword">Confirm Password</label>
                            <input
                                id="confirmPassword"
                                type="password"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                placeholder="Confirm your password"
                                required
                            />
                        </div>
                    )}

                    {error && <p className="user-error">{error}</p>}

                    <button 
                        type="submit" 
                        className="user-submit"
                        disabled={loading}
                    >
                        {loading ? "Please wait..." : isLogin ? "Login" : "Create Account"}
                    </button>
                </form>

                <div className="user-toggle">
                    {isLogin ? (
                        <p>
                            Don't have an account?{" "}
                            <button type="button" onClick={toggleMode}>
                                Sign up
                            </button>
                        </p>
                    ) : (
                        <p>
                            Already have an account?{" "}
                            <button type="button" onClick={toggleMode}>
                                Login
                            </button>
                        </p>
                    )}
                </div>
            </div>
        </div>
    );
}

export default Create_User;
