/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillDestroy, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";

class OpenwaChatApp extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.busService = useService("bus_service");
        this.messageContainerRef = useRef("messageContainer");

        this.state = useState({
            chats: [],
            selectedChatId: null,
            messages: [],
            newMessageText: "",
            searchTerm: "",
            isSending: false,
            showNewChatModal: false,
            newChatNumber: "",
            newChatError: "",
            isVerifyingNumber: false,
            sessionStatus: "disconnected",
            sessionName: "",
            sessionPhone: "",
            sessionPushName: "",
            loadingChats: true,
            loadingMessages: false,
            lightboxImage: null,
        });

        onWillStart(async () => {
            await this.loadSessionInfo();
            await this.loadChats();
        });

        onMounted(() => {
            // Subscribe to this user's private bus channel
            const uid = user.userId;
            const channel = `openwa_channel_${uid}`;
            this.busService.addChannel(channel);
            this.busService.subscribe("openwa_message", (payload) => {
                this.handleIncomingNotification(payload);
            });
            this.scrollToBottom();
        });

        onWillDestroy(() => {});
    }

    async loadSessionInfo() {
        try {
            const info = await this.orm.call("openwa.session", "get_my_session_info", []);
            this.state.sessionStatus = info.status || "disconnected";
            this.state.sessionName = info.session_name || "";
            this.state.sessionPhone = info.phone || "";
            this.state.sessionPushName = info.push_name || "";
        } catch (e) {
            console.error("Failed to load session info:", e);
        }
    }

    async loadChats() {
        this.state.loadingChats = true;
        try {
            const chats = await this.orm.call("openwa.chat", "get_chat_list", []);
            this.state.chats = chats;
        } catch (e) {
            console.error("Failed to load chats:", e);
        } finally {
            this.state.loadingChats = false;
        }
    }

    get filteredChats() {
        if (!this.state.searchTerm) return this.state.chats;
        const term = this.state.searchTerm.toLowerCase();
        return this.state.chats.filter(c =>
            (c.name && c.name.toLowerCase().includes(term)) ||
            (c.jid && c.jid.toLowerCase().includes(term))
        );
    }

    get selectedChat() {
        return this.state.chats.find(c => c.id === this.state.selectedChatId);
    }

    async selectChat(chatId) {
        if (this.state.selectedChatId === chatId) return;
        this.state.selectedChatId = chatId;
        this.state.loadingMessages = true;
        this.state.messages = [];
        this.state.newMessageText = "";

        const chat = this.state.chats.find(c => c.id === chatId);
        if (chat) chat.unread_count = 0;

        try {
            await this.orm.call("openwa.chat", "write", [[chatId], { unread_count: 0 }]);
            const messages = await this.orm.call("openwa.message", "get_messages_for_chat", [chatId]);
            this.state.messages = messages;
            this.scrollToBottom();
        } catch (e) {
            console.error("Failed to load messages:", e);
            this.notification.add("Failed to load message history", { type: "danger" });
        } finally {
            this.state.loadingMessages = false;
        }
    }

    scrollToBottom() {
        setTimeout(() => {
            const el = this.messageContainerRef.el;
            if (el) el.scrollTop = el.scrollHeight;
        }, 80);
    }

    async sendMessage() {
        const text = this.state.newMessageText.trim();
        if (!text || this.state.isSending || !this.state.selectedChatId) return;

        this.state.isSending = true;
        try {
            const newMsg = await this.orm.call("openwa.message", "send_message", [
                this.state.selectedChatId, text, false, false, false
            ]);
            if (!this.state.messages.some(m => m.id === newMsg.id)) {
                this.state.messages.push(newMsg);
            }
            this.state.newMessageText = "";
            this.scrollToBottom();
            const chat = this.state.chats.find(c => c.id === this.state.selectedChatId);
            if (chat) {
                chat.last_message_body = text;
                chat.last_message_date = newMsg.timestamp;
                this.resortChats();
            }
        } catch (e) {
            console.error("Failed to send message:", e);
            this.notification.add(e.data?.message || e.message || "Failed to send message", { type: "danger" });
        } finally {
            this.state.isSending = false;
        }
    }

    async triggerFileUpload() {
        const el = document.getElementById("openwa_chat_file_input");
        if (el) el.click();
    }

    async onFileSelected(ev) {
        const file = ev.target.files[0];
        if (!file || !this.state.selectedChatId) return;
        if (file.size > 15 * 1024 * 1024) {
            this.notification.add("File too large (max 15MB)", { type: "warning" });
            return;
        }
        const isImage = file.type && file.type.startsWith("image/");
        const reader = new FileReader();
        this.state.isSending = true;
        reader.onload = async () => {
            try {
                const b64 = reader.result.split(",")[1];
                const newMsg = await this.orm.call("openwa.message", "send_message", [
                    this.state.selectedChatId, "", b64, file.name, file.type, isImage ? "image" : "document"
                ]);
                if (!this.state.messages.some(m => m.id === newMsg.id)) {
                    this.state.messages.push(newMsg);
                }
                this.scrollToBottom();
                const chat = this.state.chats.find(c => c.id === this.state.selectedChatId);
                if (chat) {
                    chat.last_message_body = isImage ? "[Image]" : file.name;
                    chat.last_message_date = newMsg.timestamp;
                    this.resortChats();
                }
            } catch (e) {
                this.notification.add(e.data?.message || e.message || "Failed to send file", { type: "danger" });
            } finally {
                this.state.isSending = false;
                ev.target.value = "";
            }
        };
        reader.onerror = () => { this.notification.add("Failed to read file", { type: "danger" }); this.state.isSending = false; };
        reader.readAsDataURL(file);
    }

    openNewChatModal() {
        this.state.newChatNumber = "";
        this.state.newChatError = "";
        this.state.showNewChatModal = true;
    }

    closeNewChatModal() {
        this.state.showNewChatModal = false;
    }

    async createNewChat() {
        const number = this.state.newChatNumber.trim();
        if (!number) { this.state.newChatError = "Please enter a valid phone number."; return; }
        this.state.isVerifyingNumber = true;
        this.state.newChatError = "";
        try {
            const chatInfo = await this.orm.call("openwa.chat", "search_and_add_chat", [number]);
            this.state.showNewChatModal = false;
            await this.loadChats();
            await this.selectChat(chatInfo.id);
        } catch (e) {
            this.state.newChatError = e.data?.message || e.message || "Number does not exist on WhatsApp.";
        } finally {
            this.state.isVerifyingNumber = false;
        }
    }

    handleIncomingNotification(payload) {
        const event = payload.type;
        const msg = payload.message;
        if (!msg) return;

        const isForSelectedChat = msg.chat_id === this.state.selectedChatId;
        const existingChat = this.state.chats.find(c => c.id === msg.chat_id);
        if (!existingChat) { this.loadChats(); return; }

        if (event === "message_received" || event === "message_sent") {
            if (isForSelectedChat) {
                if (!this.state.messages.some(m => m.id === msg.id)) {
                    this.state.messages.push(msg);
                    this.scrollToBottom();
                    if (event === "message_received") {
                        this.orm.call("openwa.chat", "write", [[msg.chat_id], { unread_count: 0 }]);
                    }
                }
            } else if (event === "message_received") {
                existingChat.unread_count += 1;
            }
            existingChat.last_message_body = msg.body;
            existingChat.last_message_date = msg.timestamp;
            this.resortChats();
        }
    }

    resortChats() {
        this.state.chats.sort((a, b) => new Date(b.last_message_date) - new Date(a.last_message_date));
    }

    openLightbox(imageUrl) { this.state.lightboxImage = imageUrl; }
    closeLightbox() { this.state.lightboxImage = null; }

    formatTime(dateStr) {
        if (!dateStr) return "";
        try { return new Date(dateStr + " UTC").toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
        catch (e) { return ""; }
    }
}

OpenwaChatApp.template = "openwa_whatsapp.ChatApp";
registry.category("actions").add("openwa_whatsapp_chat_client_action", OpenwaChatApp);
