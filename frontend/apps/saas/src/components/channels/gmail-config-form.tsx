"use client"

import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import { IconX } from "@tabler/icons-react"
import { GmailConfig } from "@/lib/services/channels.service"

interface GmailConfigFormProps {
  config: Partial<GmailConfig>
  onChange: (config: Partial<GmailConfig>) => void
}

const DEFAULT_LABELS = ["INBOX", "IMPORTANT", "STARRED", "SENT"]
const DEFAULT_ATTACHMENT_TYPES = ["pdf", "docx", "doc", "xlsx", "xls", "txt", "pptx"]

export function GmailConfigForm({ config, onChange }: GmailConfigFormProps) {
  const labels = config.labels || ["INBOX"]
  const maxAgeDays = config.max_age_days || 90
  const includeAttachments = config.include_attachments ?? true
  const attachmentTypes = config.attachment_types || DEFAULT_ATTACHMENT_TYPES
  const maxEmailsPerSync = config.max_emails_per_sync || 100

  const toggleLabel = (label: string) => {
    const newLabels = labels.includes(label)
      ? labels.filter((l) => l !== label)
      : [...labels, label]

    // Prevent empty labels - at least INBOX must be selected
    if (newLabels.length === 0) {
      return // Don't allow removing the last label
    }

    onChange({ ...config, labels: newLabels })
  }

  const toggleAttachmentType = (type: string) => {
    const newTypes = attachmentTypes.includes(type)
      ? attachmentTypes.filter((t) => t !== type)
      : [...attachmentTypes, type]
    onChange({ ...config, attachment_types: newTypes })
  }

  return (
    <div className="space-y-6">
      {/* Labels to sync */}
      <div className="space-y-2">
        <Label>Gmail Labels to Sync</Label>
        <p className="text-xs text-muted-foreground">
          Select which labels/folders to index
        </p>
        <div className="flex flex-wrap gap-2 mt-2">
          {DEFAULT_LABELS.map((label) => (
            <Badge
              key={label}
              variant={labels.includes(label) ? "default" : "outline"}
              className="cursor-pointer"
              onClick={() => toggleLabel(label)}
            >
              {label}
              {labels.includes(label) && (
                <IconX className="h-3 w-3 ml-1" />
              )}
            </Badge>
          ))}
        </div>
      </div>

      {/* Max age */}
      <div className="space-y-2">
        <Label htmlFor="max_age_days">Maximum Email Age (days)</Label>
        <p className="text-xs text-muted-foreground">
          Only sync emails from the last N days
        </p>
        <Input
          id="max_age_days"
          type="number"
          min={1}
          max={365}
          value={maxAgeDays}
          onChange={(e) =>
            onChange({ ...config, max_age_days: parseInt(e.target.value) || 90 })
          }
          className="w-32"
        />
      </div>

      {/* Max emails per sync */}
      <div className="space-y-2">
        <Label htmlFor="max_emails_per_sync">Max Emails per Sync</Label>
        <p className="text-xs text-muted-foreground">
          Limit the number of emails processed in each sync
        </p>
        <Input
          id="max_emails_per_sync"
          type="number"
          min={10}
          max={500}
          value={maxEmailsPerSync}
          onChange={(e) =>
            onChange({
              ...config,
              max_emails_per_sync: parseInt(e.target.value) || 100,
            })
          }
          className="w-32"
        />
      </div>

      {/* Include attachments */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label>Include Attachments</Label>
          <p className="text-xs text-muted-foreground">
            Also index PDF, Word, Excel attachments
          </p>
        </div>
        <Switch
          checked={includeAttachments}
          onCheckedChange={(checked) =>
            onChange({ ...config, include_attachments: checked })
          }
        />
      </div>

      {/* Attachment types */}
      {includeAttachments && (
        <div className="space-y-2">
          <Label>Attachment Types</Label>
          <p className="text-xs text-muted-foreground">
            Select which file types to process
          </p>
          <div className="flex flex-wrap gap-2 mt-2">
            {DEFAULT_ATTACHMENT_TYPES.map((type) => (
              <Badge
                key={type}
                variant={attachmentTypes.includes(type) ? "default" : "outline"}
                className="cursor-pointer"
                onClick={() => toggleAttachmentType(type)}
              >
                .{type}
                {attachmentTypes.includes(type) && (
                  <IconX className="h-3 w-3 ml-1" />
                )}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Info box */}
      <div className="rounded-lg bg-blue-50 dark:bg-blue-900/20 p-3 text-sm text-blue-700 dark:text-blue-300">
        <p className="font-medium mb-1">After creating the channel:</p>
        <p>
          You&apos;ll be redirected to Google to authorize access to your Gmail account.
          We only request read-only access.
        </p>
      </div>
    </div>
  )
}
