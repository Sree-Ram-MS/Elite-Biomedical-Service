/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillDestroy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class OpenwaSessionDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            actionLoading: false,
            has_session: false,
            status: "not_created",
            session_name: "",
            phone: "",
            push_name: "",
            qr_code: null,
        });

        this._prevStatus = null;

        onWillStart(async () => {
            await this.refresh();
        });

        onMounted(() => {
            // Auto-poll during transitional states every 3 seconds
            this.pollInterval = setInterval(async () => {
                const s = this.state.status;
                if (["initializing", "authenticating", "qr_ready"].includes(s)) {
                    await this.refresh(true);  // silent refresh
                }
            }, 3000);
        });

        onWillDestroy(() => {
            if (this.pollInterval) clearInterval(this.pollInterval);
        });
    }

    async refresh(silent = false) {
        if (!silent) this.state.loading = true;
        try {
            const prevStatus = this.state.status;
            // Always poll NestJS for fresh status when session exists
            const method = this.state.has_session ? "refresh_my_status" : "get_my_session_info";
            const info = await this.orm.call("openwa.session", method, []);
            Object.assign(this.state, info);

            // Show success notification when transitioning to "ready"
            if (prevStatus !== "ready" && info.status === "ready") {
                this.notification.add(
                    `🎉 WhatsApp Connected! Welcome, ${info.push_name || info.phone || "User"}.`,
                    { type: "success", sticky: false }
                );
            }
        } catch (e) {
            console.error("Failed to load session info:", e);
        } finally {
            this.state.loading = false;
        }
    }

    async createSession() {
        this.state.actionLoading = true;
        try {
            const info = await this.orm.call("openwa.session", "action_create_my_session", []);
            Object.assign(this.state, info);
            this.notification.add(
                `Session '${info.session_name}' created! Click 'Start Engine' to connect.`,
                { type: "success" }
            );
        } catch (e) {
            this.notification.add(e.data?.message || e.message || "Failed to create session.", { type: "danger" });
        } finally {
            this.state.actionLoading = false;
        }
    }

    async startSession() {
        this.state.actionLoading = true;
        try {
            const info = await this.orm.call("openwa.session", "action_start_my_session", []);
            Object.assign(this.state, info);
            this.notification.add(
                "WhatsApp engine starting… Please wait for the QR code (15–30 seconds).",
                { type: "info" }
            );
        } catch (e) {
            this.notification.add(e.data?.message || e.message || "Failed to start session.", { type: "danger" });
        } finally {
            this.state.actionLoading = false;
        }
    }

    async stopSession() {
        if (!confirm("Stop your WhatsApp session? You will be disconnected.")) return;
        this.state.actionLoading = true;
        try {
            const info = await this.orm.call("openwa.session", "action_stop_my_session", []);
            Object.assign(this.state, info);
            this.notification.add("Session stopped.", { type: "info" });
        } catch (e) {
            this.notification.add(e.data?.message || e.message || "Failed to stop session.", { type: "danger" });
        } finally {
            this.state.actionLoading = false;
        }
    }

    async deleteSession() {
        if (!confirm("Delete and wipe your session from the server? This cannot be undone.")) return;
        this.state.actionLoading = true;
        try {
            const info = await this.orm.call("openwa.session", "action_delete_my_session", []);
            Object.assign(this.state, info);
            this.notification.add("Session deleted.", { type: "info" });
        } catch (e) {
            this.notification.add(e.data?.message || e.message || "Failed to delete session.", { type: "danger" });
        } finally {
            this.state.actionLoading = false;
        }
    }

    get statusLabel() {
        const map = {
            not_created: "Not Created",
            disconnected: "Disconnected",
            initializing: "Initializing…",
            qr_ready: "Scan QR Code",
            authenticating: "Authenticating…",
            ready: "Connected ✓",
            failed: "Failed",
        };
        return map[this.state.status] || this.state.status;
    }

    get statusColor() {
        const map = {
            ready: "success",
            qr_ready: "warning",
            initializing: "warning",
            authenticating: "warning",
            disconnected: "danger",
            not_created: "secondary",
            failed: "danger",
        };
        return map[this.state.status] || "secondary";
    }
}

OpenwaSessionDashboard.template = "openwa_whatsapp.SessionDashboard";
registry.category("actions").add("openwa_whatsapp_session_dashboard", OpenwaSessionDashboard);
