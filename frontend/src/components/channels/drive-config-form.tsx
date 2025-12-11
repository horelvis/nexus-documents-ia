"use client"

import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import { IconX, IconFolder } from "@tabler/icons-react"
import { GoogleDriveConfig } from "@/lib/services/channels.service"

interface DriveConfigFormProps {
  config: Partial<GoogleDriveConfig>
  onChange: (config: Partial<GoogleDriveConfig>) => void
}

const DEFAULT_FILE_TYPES = ["pdf", "docx", "doc", "xlsx", "xls", "txt", "pptx", "ppt"]

export function DriveConfigForm({ config, onChange }: DriveConfigFormProps) {
  const folderId = config.folder_id || ""
  const folderName = config.folder_name || ""
  const includeSubfolders = config.include_subfolders ?? true
  const fileTypes = config.file_types || DEFAULT_FILE_TYPES
  const maxFileSizeMb = config.max_file_size_mb || 50

  const toggleFileType = (type: string) => {
    const newTypes = fileTypes.includes(type)
      ? fileTypes.filter((t) => t !== type)
      : [...fileTypes, type]
    onChange({ ...config, file_types: newTypes })
  }

  // Extract folder ID from URL if pasted
  const handleFolderIdChange = (value: string) => {
    // Handle full Drive folder URL
    const urlMatch = value.match(/folders\/([a-zA-Z0-9_-]+)/)
    const folderId = urlMatch ? urlMatch[1] : value
    onChange({ ...config, folder_id: folderId })
  }

  return (
    <div className="space-y-6">
      {/* Folder ID */}
      <div className="space-y-2">
        <Label htmlFor="folder_id">Google Drive Folder</Label>
        <p className="text-xs text-muted-foreground">
          Paste the folder URL or ID from Google Drive
        </p>
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <IconFolder className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              id="folder_id"
              value={folderId}
              onChange={(e) => handleFolderIdChange(e.target.value)}
              placeholder="Folder ID or URL"
              className="pl-9"
            />
          </div>
        </div>
        {folderId && (
          <p className="text-xs text-muted-foreground">
            Folder ID: <code className="bg-muted px-1 rounded">{folderId}</code>
          </p>
        )}
      </div>

      {/* Folder name (optional, for display) */}
      <div className="space-y-2">
        <Label htmlFor="folder_name">Folder Name (optional)</Label>
        <p className="text-xs text-muted-foreground">
          A friendly name to identify this folder
        </p>
        <Input
          id="folder_name"
          value={folderName}
          onChange={(e) => onChange({ ...config, folder_name: e.target.value })}
          placeholder="e.g., Project Documents"
        />
      </div>

      {/* Include subfolders */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label>Include Subfolders</Label>
          <p className="text-xs text-muted-foreground">
            Also sync files in nested folders
          </p>
        </div>
        <Switch
          checked={includeSubfolders}
          onCheckedChange={(checked) =>
            onChange({ ...config, include_subfolders: checked })
          }
        />
      </div>

      {/* Max file size */}
      <div className="space-y-2">
        <Label htmlFor="max_file_size_mb">Maximum File Size (MB)</Label>
        <p className="text-xs text-muted-foreground">
          Skip files larger than this size
        </p>
        <Input
          id="max_file_size_mb"
          type="number"
          min={1}
          max={100}
          value={maxFileSizeMb}
          onChange={(e) =>
            onChange({
              ...config,
              max_file_size_mb: parseInt(e.target.value) || 50,
            })
          }
          className="w-32"
        />
      </div>

      {/* File types */}
      <div className="space-y-2">
        <Label>File Types to Sync</Label>
        <p className="text-xs text-muted-foreground">
          Select which file types to index
        </p>
        <div className="flex flex-wrap gap-2 mt-2">
          {DEFAULT_FILE_TYPES.map((type) => (
            <Badge
              key={type}
              variant={fileTypes.includes(type) ? "default" : "outline"}
              className="cursor-pointer"
              onClick={() => toggleFileType(type)}
            >
              .{type}
              {fileTypes.includes(type) && (
                <IconX className="h-3 w-3 ml-1" />
              )}
            </Badge>
          ))}
        </div>
      </div>

      {/* Info box */}
      <div className="rounded-lg bg-blue-50 dark:bg-blue-900/20 p-3 text-sm text-blue-700 dark:text-blue-300">
        <p className="font-medium mb-1">After creating the channel:</p>
        <p>
          You&apos;ll be redirected to Google to authorize access to your Drive.
          We only request read-only access to the specified folder.
        </p>
      </div>

      {/* How to get folder ID */}
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
          How to get the folder ID?
        </summary>
        <div className="mt-2 pl-4 border-l-2 border-muted text-muted-foreground">
          <ol className="list-decimal list-inside space-y-1">
            <li>Open Google Drive in your browser</li>
            <li>Navigate to the folder you want to sync</li>
            <li>Copy the URL from the address bar</li>
            <li>Paste it here - we&apos;ll extract the folder ID automatically</li>
          </ol>
          <p className="mt-2 text-xs">
            Example URL: https://drive.google.com/drive/folders/<strong>1ABC123xyz</strong>
          </p>
        </div>
      </details>
    </div>
  )
}
