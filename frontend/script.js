document.addEventListener('DOMContentLoaded', () => {
    
    // --- DOM ELEMENTS ---
    const landingView = document.getElementById('landing-view');
    const chatView = document.getElementById('chat-view');
    
    // Upload Elements
    const dropArea = document.getElementById('drop-area');
    const fileInput = document.getElementById('file-input');
    const browseBtn = document.getElementById('browse-btn');
    const fileInfo = document.getElementById('file-info');
    const filenameDisplay = document.getElementById('filename-display');
    const removeFileBtn = document.getElementById('remove-file-btn');
    const uploadBtn = document.getElementById('upload-btn');
    const uploadBtnText = uploadBtn.querySelector('span');
    const uploadBtnIcon = uploadBtn.querySelector('i');

    // Chat Elements
    const chatDocName = document.getElementById('chat-doc-name');
    const chatHistory = document.getElementById('chat-history');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const newChatBtn = document.getElementById('new-chat-btn');

    // --- STATE ---
    let selectedFile = null;
    let currentDocId = null; 

    // --- DRAG & DROP ---
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, (e) => { e.preventDefault(); e.stopPropagation(); }, false);
    });

    ['dragenter', 'dragover'].forEach(evt => dropArea.addEventListener(evt, () => dropArea.classList.add('highlight'), false));
    ['dragleave', 'drop'].forEach(evt => dropArea.addEventListener(evt, () => dropArea.classList.remove('highlight'), false));

    dropArea.addEventListener('drop', (e) => handleFiles(e.dataTransfer.files), false);

    // --- BROWSE ---
    browseBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', function() { handleFiles(this.files); });

    function handleFiles(files) {
        if (files.length > 0) {
            const file = files[0];
            if (file.type === 'application/pdf' || file.name.endsWith('.txt') || file.name.endsWith('.pdf')) {
                selectedFile = file;
                updateFileUI();
            } else {
                showToast("Only PDF or TXT files are allowed.", "error");
            }
        }
    }

    function updateFileUI() {
        if (selectedFile) {
            dropArea.classList.add('hidden');
            fileInfo.classList.remove('hidden');
            filenameDisplay.textContent = selectedFile.name;
            uploadBtn.disabled = false;
        } else {
            dropArea.classList.remove('hidden');
            fileInfo.classList.add('hidden');
            uploadBtn.disabled = true;
            fileInput.value = '';
        }
    }

    removeFileBtn.addEventListener('click', () => { selectedFile = null; updateFileUI(); });

    // --- UPLOAD ---
    uploadBtn.addEventListener('click', async () => {
        if (!selectedFile) return;

        uploadBtn.disabled = true;
        uploadBtnText.textContent = "Analyzing Document...";
        uploadBtnIcon.className = "spinner"; 

        const formData = new FormData();
        formData.append('file', selectedFile);

        try {
            const response = await fetch('/upload', { method: 'POST', body: formData });
            const data = await response.json();

            if (response.ok) {
                currentDocId = data.doc_id;
                chatDocName.textContent = selectedFile.name;
                switchToChatView();
            } else {
                showToast(data.error || "Upload failed.", "error");
                resetUploadBtn();
            }
        } catch (error) {
            showToast("Connection error. Is backend running?", "error");
            resetUploadBtn();
        }
    });

    function resetUploadBtn() {
        uploadBtn.disabled = false;
        uploadBtnText.textContent = "Analyze Document";
        uploadBtnIcon.className = "fa-solid fa-arrow-right";
    }

    function switchToChatView() {
        landingView.classList.remove('active');
        setTimeout(() => {
            landingView.style.display = 'none'; 
            chatView.classList.remove('hidden');
            requestAnimationFrame(() => chatView.classList.add('active'));
        }, 500);
    }

    // --- CHAT LOGIC ---
    userInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        sendBtn.disabled = this.value.trim() === '';
    });

    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    });

    sendBtn.addEventListener('click', handleSend);

    async function handleSend() {
        const question = userInput.value.trim();
        if (!question) return;

        addMessage(question, 'user');
        userInput.value = '';
        userInput.style.height = 'auto';
        sendBtn.disabled = true;

        const loadingId = addTypingIndicator();

        try {
            const response = await fetch('/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: question, doc_id: currentDocId })
            });

            // Parse safely
            let data;
            try { data = await response.json(); } catch (e) { throw new Error("Server returned invalid JSON"); }

            removeMessage(loadingId);
            
            if (!response.ok) {
                const errorMsg = data.error || data.answer || "Unknown server error";
                addMessage(`⚠️ ${errorMsg}`, 'bot');
            } else {
                // *** HANDLE RESPONSE MODES ***
                
                // 1. Text Explanation
                let finalHtml = data.answer || "Here is what I found.";
                
                // 2. Add Sources (if any)
                if (data.sources && data.sources.length > 0) {
                    finalHtml += "<br><br><strong>Sources:</strong><br>";
                    data.sources.forEach(source => {
                        finalHtml += `<small>📄 <em>"${source.snippet || '...'}"</em></small><br>`;
                    });
                }

                // Add text bubble
                addMessage(finalHtml, 'bot');

                // 3. Handle VISUALIZATION
                if (data.mode === 'visualization' && data.chart_config) {
                    addChartBubble(data.chart_config);
                }
            }

        } catch (error) {
            console.error(error);
            removeMessage(loadingId);
            addMessage("❌ Error: " + error.message, 'bot');
        }
    }

    function addMessage(text, sender) {
        const msgDiv = document.createElement('div');
        msgDiv.classList.add('message');
        msgDiv.classList.add(sender === 'user' ? 'user-message' : 'bot-message');

        const avatarDiv = document.createElement('div');
        avatarDiv.classList.add('avatar');
        avatarDiv.innerHTML = sender === 'user' ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-robot"></i>';

        const contentDiv = document.createElement('div');
        contentDiv.classList.add('message-content');
        
        let formattedText = text
            .replace(/\n/g, '<br>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>');
            
        contentDiv.innerHTML = formattedText;

        if (sender === 'user') {
            msgDiv.appendChild(contentDiv); 
            msgDiv.appendChild(avatarDiv); 
        } else {
            msgDiv.appendChild(avatarDiv);
            msgDiv.appendChild(contentDiv);
        }

        chatHistory.appendChild(msgDiv);
        scrollToBottom();
    }

    function addChartBubble(config) {
        const msgDiv = document.createElement('div');
        msgDiv.classList.add('message', 'bot-message');
        
        const avatarDiv = document.createElement('div');
        avatarDiv.classList.add('avatar');
        avatarDiv.innerHTML = '<i class="fa-solid fa-chart-simple"></i>';

        const contentDiv = document.createElement('div');
        contentDiv.classList.add('message-content');
        contentDiv.style.width = '100%'; // Full width for chart

        // Create Canvas for Chart.js
        const canvas = document.createElement('canvas');
        canvas.style.maxWidth = '100%';
        canvas.style.maxHeight = '400px';
        contentDiv.appendChild(canvas);

        msgDiv.appendChild(avatarDiv);
        msgDiv.appendChild(contentDiv);
        chatHistory.appendChild(msgDiv);
        scrollToBottom();

        // Render Chart
        try {
            new Chart(canvas, config);
        } catch (e) {
            contentDiv.innerHTML = "❌ Error rendering chart.";
            console.error(e);
        }
    }

    function addTypingIndicator() {
        const id = 'loader-' + Date.now();
        const msgDiv = document.createElement('div');
        msgDiv.classList.add('message', 'bot-message');
        msgDiv.id = id;
        msgDiv.innerHTML = `
            <div class="avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="message-content"><div class="typing-indicator"><span></span><span></span><span></span></div></div>
        `;
        chatHistory.appendChild(msgDiv);
        scrollToBottom();
        return id;
    }

    function removeMessage(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function scrollToBottom() {
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    function showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.classList.add('toast');
        if (type === 'error') toast.style.backgroundColor = '#ef4444';
        toast.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> ${message}`;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    newChatBtn.addEventListener('click', () => {
        if(confirm("Start a new chat?")) window.location.reload();
    });
});