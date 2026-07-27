Get-ChildItem 'C:\Users\moral\.gemini\antigravity-ide\scratch\Project_State\Audit' -ErrorAction SilentlyContinue | Select-Object Name, LastWriteTime, Length | Format-Table -AutoSize
