const chatBox = document.getElementById('chat-container');
const input = document.getElementById('user-input');
const menuBtn = document.getElementById('menu-btn');
const sidebar = document.getElementById('sidebar');

// Sidebar toggle
menuBtn.addEventListener('click', () => sidebar.classList.add('open'));
document.getElementById('close-menu').addEventListener('click', () => sidebar.classList.remove('open'));

document.getElementById('send-btn').addEventListener('click', sendMessage);

async function sendMessage() {
    const text = input.value;
    if (!text) return;

    appendMessage("You", text, 'user');
    input.value = '';
    
    document.getElementById('thinking-indicator').classList.remove('hidden');

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });
        const data = await response.json();
        
        document.getElementById('thinking-indicator').classList.add('hidden');
        streamMessage("B.E.T.A", data.response);
    } catch (e) {
        document.getElementById('thinking-indicator').classList.add('hidden');
    }
}

function appendMessage(sender, text, className) {
    const div = document.createElement('div');
    div.className = `bubble ${className}`;
    div.innerText = text;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function streamMessage(sender, text) {
    const div = document.createElement('div');
    div.className = 'bubble ai';
    chatBox.appendChild(div);
    
    let i = 0;
    const interval = setInterval(() => {
        div.innerText += text.charAt(i);
        i++;
        chatBox.scrollTop = chatBox.scrollHeight;
        if (i >= text.length) clearInterval(interval);
    }, 30);
}
