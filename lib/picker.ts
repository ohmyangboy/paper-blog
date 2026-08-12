import { execSync } from 'child_process';
import os from 'os';

/**
 * 跨平台唤起系统原生 GUI 文件夹选择窗口
 * 返回选择的绝对路径，如果取消或不支持则返回 null
 */
export function openNativeFolderPicker(title = '请选择你的 Markdown 文章存储文件夹'): string | null {
  const platform = os.platform();

  try {
    if (platform === 'darwin') {
      // macOS: 使用 AppleScript 唤起 Finder 选择器
      const script = `POSIX path of (choose folder with prompt "${title}")`;
      const result = execSync(`osascript -e '${script}'`, { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'ignore'] });
      const dirPath = result.trim();
      return dirPath || null;
    } else if (platform === 'win32') {
      // Windows: 使用 PowerShell FolderBrowserDialog 窗口
      const psCommand = `
        Add-Type -AssemblyName System.Windows.Forms;
        $f = New-Object System.Windows.Forms.FolderBrowserDialog;
        $f.Description = "${title}";
        if ($f.ShowDialog() -eq 'OK') { Write-Output $f.SelectedPath }
      `.replace(/\n/g, ' ');

      const result = execSync(`powershell -Command "${psCommand}"`, { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'ignore'] });
      const dirPath = result.trim();
      return dirPath || null;
    } else if (platform === 'linux') {
      // Linux: 尝试使用 zenity
      const result = execSync(`zenity --file-selection --directory --title="${title}"`, { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'ignore'] });
      const dirPath = result.trim();
      return dirPath || null;
    }
  } catch {
    // 用户在 GUI 窗口取消选择或环境不支持 GUI
    return null;
  }

  return null;
}
