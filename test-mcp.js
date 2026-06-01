const fs = require('fs');
const log = fs.createWriteStream('C:/neoSlice/test-mcp.log', {flags:'a'});
log.write(`[${new Date().toISOString()}] STARTED\n`);
process.stdin.on('data', (d) => {
  log.write(`[IN] ${d}\n`);
  try {
    const msg = JSON.parse(d.toString().trim());
    if (msg.method === 'initialize') {
      const r = JSON.stringify({jsonrpc:'2.0',id:msg.id,result:{protocolVersion:'2024-11-05',capabilities:{tools:{}},serverInfo:{name:'test',version:'1.0'}}});
      log.write(`[OUT] ${r}\n`);
      process.stdout.write(r + '\n');
    }
  } catch(e) { log.write(`[ERR] ${e}\n`); }
});
process.on('exit', () => log.write(`[${new Date().toISOString()}] EXIT\n`));
