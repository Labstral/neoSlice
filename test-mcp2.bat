@echo off
echo SPAWNED > C:\neoSlice\spawn-test.log
date /t >> C:\neoSlice\spawn-test.log
time /t >> C:\neoSlice\spawn-test.log
C:\neoSlice\nodex.exe C:\neoSlice\test-mcp.js
