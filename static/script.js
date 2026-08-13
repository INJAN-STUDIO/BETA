const chatBox = document.getElementById('chat-container');
const input = document.getElementById('user-input');

// Menu toggle
document.getElementById('menu-btn').addEventListener('click', () => document.getElementById('sidebar').classList.add('open'));
document.getElementById('close-menu').addEventListener('click', () => document.getElementById('sidebar').classList.remove('open'));

// Send message (Click & Enter)
document.getElementById('send-btn').addEventListener('click', sendMessage);
input.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });

async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;

    // UI: Add User Message
    addBubble(text, 'user');
    input.value = '';

    // UI: Add AI Placeholder
    const aiBubble = addBubble("...", 'ai');

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });
        const data = await response.json();
        
        // Remove placeholder and stream response
        aiBubble.innerText = '';
        streamText(aiBubble, data.response);
    } catch (e) {
        aiBubble.innerText = "Error: B.E.T.A. is offline.";
    }
}

function addBubble(text, className) {
    const div = document.createElement('div');
    div.className = `bubble ${className}`;
    div.innerText = text;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
    return div;
}

function streamText(element, text) {
    let i = 0;
    const interval = setInterval(() => {
        element.innerText += text.charAt(i);
        i++;
        chatBox.scrollTop = chatBox.scrollHeight;
        if (i >= text.length) clearInterval(interval);
    }, 25);
}
