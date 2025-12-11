"use client"

import { useState } from "react"
import {
  IconMail,
  IconBrandGoogleDrive,
  IconDatabase,
  IconUsers,
  IconUser,
  IconArrowLeft,
  IconArrowRight,
  IconLoader2,
} from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { useToast } from "@/hooks/use-toast"
import {
  useChannelsService,
  Channel,
  ChannelType,
  ChannelVisibility,
  DEFAULT_GMAIL_CONFIG,
  DEFAULT_DRIVE_CONFIG,
} from "@/lib/services/channels.service"
import { GmailConfigForm } from "./gmail-config-form"
import { DriveConfigForm } from "./drive-config-form"
import { useTranslation } from "@/lib/i18n/hooks"

interface CreateChannelDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (channel: Channel) => void
}

type Step = "type" | "visibility" | "details" | "config"

const CHANNEL_TYPE_ICONS = {
  gmail: { icon: IconMail, color: "text-red-500 bg-red-50 dark:bg-red-900/20" },
  google_drive: { icon: IconBrandGoogleDrive, color: "text-blue-500 bg-blue-50 dark:bg-blue-900/20" },
  external_db: { icon: IconDatabase, color: "text-purple-500 bg-purple-50 dark:bg-purple-900/20", disabled: true },
}

const VISIBILITY_ICONS = {
  personal: IconUser,
  tenant: IconUsers,
}

export function CreateChannelDialog({
  open,
  onOpenChange,
  onCreated,
}: CreateChannelDialogProps) {
  const { toast } = useToast()
  const { t } = useTranslation()
  const channelsService = useChannelsService()

  // Wizard state
  const [step, setStep] = useState<Step>("type")
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Form state
  const [channelType, setChannelType] = useState<ChannelType | null>(null)
  const [visibility, setVisibility] = useState<ChannelVisibility>("personal")
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [configuration, setConfiguration] = useState<Record<string, any>>({})

  // Reset form when dialog closes
  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      setStep("type")
      setChannelType(null)
      setVisibility("personal")
      setName("")
      setDescription("")
      setConfiguration({})
    }
    onOpenChange(isOpen)
  }

  // Navigation
  const canGoNext = (): boolean => {
    switch (step) {
      case "type":
        return channelType !== null
      case "visibility":
        return true
      case "details":
        return name.trim().length > 0
      case "config":
        return true
      default:
        return false
    }
  }

  const goNext = () => {
    switch (step) {
      case "type":
        setStep("visibility")
        break
      case "visibility":
        setStep("details")
        break
      case "details":
        // Set default config based on type
        if (channelType === "gmail") {
          setConfiguration(DEFAULT_GMAIL_CONFIG)
        } else if (channelType === "google_drive") {
          setConfiguration(DEFAULT_DRIVE_CONFIG)
        }
        setStep("config")
        break
    }
  }

  const goBack = () => {
    switch (step) {
      case "visibility":
        setStep("type")
        break
      case "details":
        setStep("visibility")
        break
      case "config":
        setStep("details")
        break
    }
  }

  // Submit
  const handleSubmit = async () => {
    if (!channelType) return

    setIsSubmitting(true)

    try {
      const response = await channelsService.createChannel({
        name: name.trim(),
        description: description.trim() || undefined,
        channel_type: channelType,
        visibility,
        configuration,
        sync_interval_minutes: 60,
      })

      if (response.error) {
        toast({
          title: t("channels.toast.createError.title"),
          description: response.error,
          variant: "destructive",
        })
      } else if (response.data) {
        toast({
          title: t("channels.toast.createSuccess.title"),
          description: t("channels.toast.createSuccess.description"),
        })
        onCreated(response.data)
      }
    } catch (err) {
      toast({
        title: t("channels.toast.createError.title"),
        description: t("channels.toast.createError.description"),
        variant: "destructive",
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  // Step content
  const renderStepContent = () => {
    const channelTypes: ChannelType[] = ["gmail", "google_drive", "external_db"]
    const visibilityTypes: ChannelVisibility[] = ["personal", "tenant"]

    switch (step) {
      case "type":
        return (
          <div className="space-y-3">
            {channelTypes.map((type) => {
              const config = CHANNEL_TYPE_ICONS[type]
              const TypeIcon = config.icon
              const isDisabled = "disabled" in config && config.disabled
              return (
                <button
                  key={type}
                  onClick={() => !isDisabled && setChannelType(type)}
                  disabled={isDisabled}
                  className={`w-full flex items-start gap-3 p-4 rounded-lg border-2 transition-colors text-left ${
                    channelType === type
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  } ${isDisabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
                >
                  <div className={`rounded-lg p-2 ${config.color}`}>
                    <TypeIcon className="h-5 w-5" />
                  </div>
                  <div className="flex-1">
                    <div className="font-medium flex items-center gap-2">
                      {t(`channels.types.${type}`)}
                      {isDisabled && (
                        <span className="text-xs text-muted-foreground">
                          ({t("channels.create.dbDescription")})
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {type === "gmail" && t("channels.create.gmailDescription")}
                      {type === "google_drive" && t("channels.create.driveDescription")}
                      {type === "external_db" && t("channels.create.dbDescription")}
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        )

      case "visibility":
        return (
          <RadioGroup
            value={visibility}
            onValueChange={(v) => setVisibility(v as ChannelVisibility)}
            className="space-y-3"
          >
            {visibilityTypes.map((vis) => {
              const VisIcon = VISIBILITY_ICONS[vis]
              return (
                <label
                  key={vis}
                  className={`flex items-start gap-3 p-4 rounded-lg border-2 cursor-pointer transition-colors ${
                    visibility === vis
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  }`}
                >
                  <RadioGroupItem value={vis} className="mt-1" />
                  <div className="flex-1">
                    <div className="font-medium flex items-center gap-2">
                      <VisIcon className="h-4 w-4" />
                      {t(`channels.visibility.${vis}`)}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {t(`channels.visibility.${vis}Description`)}
                    </div>
                  </div>
                </label>
              )
            })}
          </RadioGroup>
        )

      case "details":
        return (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">{t("channels.create.channelName")} *</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("channels.create.channelNamePlaceholder")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">{t("common.edit")}</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder=""
                rows={3}
              />
            </div>
          </div>
        )

      case "config":
        if (channelType === "gmail") {
          return (
            <GmailConfigForm
              config={configuration}
              onChange={setConfiguration}
            />
          )
        } else if (channelType === "google_drive") {
          return (
            <DriveConfigForm
              config={configuration}
              onChange={setConfiguration}
            />
          )
        }
        return null
    }
  }

  const getStepTitle = () => {
    switch (step) {
      case "type":
        return t("channels.create.step1")
      case "visibility":
        return t("channels.create.selectVisibility")
      case "details":
        return t("channels.create.channelName")
      case "config":
        return channelType === "gmail" ? t("channels.gmail.title") : t("channels.drive.title")
    }
  }

  const getStepDescription = () => {
    switch (step) {
      case "type":
        return t("channels.create.selectType")
      case "visibility":
        return t("channels.create.selectVisibility")
      case "details":
        return t("channels.create.description")
      case "config":
        return t("channels.create.description")
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>{getStepTitle()}</DialogTitle>
          <DialogDescription>{getStepDescription()}</DialogDescription>
        </DialogHeader>

        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2 py-2">
          {["type", "visibility", "details", "config"].map((s, i) => (
            <div
              key={s}
              className={`h-2 w-8 rounded-full transition-colors ${
                s === step
                  ? "bg-primary"
                  : ["type", "visibility", "details", "config"].indexOf(step) > i
                  ? "bg-primary/50"
                  : "bg-muted"
              }`}
            />
          ))}
        </div>

        <div className="py-4">{renderStepContent()}</div>

        <DialogFooter className="gap-2 sm:gap-0">
          {step !== "type" && (
            <Button variant="outline" onClick={goBack} disabled={isSubmitting}>
              <IconArrowLeft className="h-4 w-4 mr-2" />
              {t("common.back")}
            </Button>
          )}

          {step !== "config" ? (
            <Button onClick={goNext} disabled={!canGoNext()}>
              {t("common.next")}
              <IconArrowRight className="h-4 w-4 ml-2" />
            </Button>
          ) : (
            <Button onClick={handleSubmit} disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <IconLoader2 className="h-4 w-4 mr-2 animate-spin" />
                  {t("channels.create.creating")}
                </>
              ) : (
                t("channels.create.createButton")
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
