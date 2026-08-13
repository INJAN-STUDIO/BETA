const chatBox = document.getElementById('chat-container');
const input = document.getElementById('user-input');

document.getElementById('menu-btn').addEventListener('click', () => document.getElementById('sidebar').classList.add('open'));
document.getElementById('close-menu').addEventListener('click', () => document.getElementById('sidebar').classList.remove('open'));

document.getElementById('send-btn').addEventListener('click', sendMessage);

// Handle Enter key for textarea
input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Auto-resize textarea
input.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;

    addBubble(text, 'user');
    input.value = '';
    input.style.height = 'auto';

    const aiBubble = addBubble("...", 'ai');

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });
        const data = await response.json();
        aiBubble.innerText = '';
        streamText(aiBubble, data.response);
    } catch (e) {
        aiBubble.innerText = "Error: B.E.T.A. is unreachable.";
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
