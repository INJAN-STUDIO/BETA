const input = document.getElementById('user-input');
const chatContainer = document.getElementById('chat-container');

async function sendMessage() {
    const message = input.value;
    if (!message) return;
    
    appendMessage("user", message);
    input.value = '';
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        });
        const data = await response.json();
        streamMessage("bot", data.response);
    } catch (e) { console.error(e); }
}

function appendMessage(sender, text) {
    const div = document.createElement('div');
    div.className = `bubble ${sender}`;
    div.innerText = text;
    chatContainer.appendChild(div);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function streamMessage(sender, text) {
    const div = document.createElement('div');
    div.className = `bubble ${sender}`;
    chatContainer.appendChild(div);
    
    let i = 0;
    const interval = setInterval(() => {
        div.innerText += text.charAt(i);
        i++;
        chatContainer.scrollTop = chatContainer.scrollHeight;
        if (i >= text.length) clearInterval(interval);
    }, 30);
}

document.getElementById('send-btn').onclick = sendMessage;
input.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
