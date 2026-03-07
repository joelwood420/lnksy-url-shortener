
export async function getMyUrls() {
    const response = await fetch("/my-urls", {
        credentials: "include",
    });
    if (response.status === 401) {
        const err = new Error("Not logged in");
        err.status = 401;
        throw err;
    }
    if (!response.ok) {
        throw new Error("Failed to load URLs");
    }
    return response.json();
}


export async function deleteUrl(shortCode) {
    const response = await fetch(`/delete/${shortCode}`, {
        method: "DELETE",
        credentials: "include",
    });
    if (!response.ok) {
        throw new Error("Failed to delete URL");
    }
    return true;
}


export async function getQrCode(shortCode) {
    const response = await fetch(`/qr/${shortCode}`);
    if (!response.ok) {
        throw new Error("Failed to load QR code");
    }
    const data = await response.json();
    return data.qr_code;
}


export async function shortenUrl(url) {
    const response = await fetch("/shorten", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({ url }),
    });
    const data = await response.json();
    if (!response.ok) {
        const err = new Error(data.error || "Something went wrong");
        err.status = response.status;
        throw err;
    }
    return data;
}


export async function getMe() {
    const response = await fetch("/me", { credentials: "include" });
    if (!response.ok) return null;
    const data = await response.json();
    return data.email || null;
}


export async function login(email, password) {
    const response = await fetch("/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || "Login failed");
    }
    return data;
}


export async function register(email, password) {
    const response = await fetch("/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || "Registration failed");
    }
    return data;
}


export async function logout() {
    const response = await fetch("/logout", {
        method: "POST",
        credentials: "include",
    });
    if (!response.ok) {
        throw new Error("Logout failed");
    }
    return response.json();
}
