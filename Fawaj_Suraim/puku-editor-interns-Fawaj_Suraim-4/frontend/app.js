// External script — avoids any inline-script / unsafe-eval CSP issues from the host preview.
const $ = (id) => document.getElementById(id);
const logs = $('logs');

let runCount = 0;

function append(text) {
  logs.textContent += text;
  logs.scrollTop = logs.scrollHeight;
}

function separator(jobId) {
  runCount += 1;
  append(`\n────── run #${runCount}  jobId=${jobId}  ──────\n`);
}

$('clear').onclick = () => {
  logs.textContent = '';
  runCount = 0;
  append('[log cleared]\n');
};

$('submit').onclick = async () => {
  const res = await fetch('/jobs', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...($('key').value ? { 'x-api-key': $('key').value } : {})
    },
    body: JSON.stringify({
      image: $('image').value,
      command: $('command').value,
    })
  });
  const { jobId } = await res.json();
  separator(jobId);

  const wsUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}?jobId=${jobId}${ $('key').value ? '&token=' + encodeURIComponent($('key').value) : '' }`;
  const ws = new WebSocket(wsUrl);
  ws.onmessage = (e) => append(e.data + '\n');
  ws.onclose = () => append('[closed]\n');
};