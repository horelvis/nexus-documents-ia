"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { toast } from "sonner"
import { Copy, Mail, Link } from "lucide-react"

interface ShareDocumentDialogProps {
  documentId: string
  documentTitle: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ShareDocumentDialog({
  documentId,
  documentTitle,
  open,
  onOpenChange,
}: ShareDocumentDialogProps) {
  const [email, setEmail] = useState("")
  const shareUrl = typeof window !== "undefined" ? window.location.href : ""

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl)
      toast.success("Link copied to clipboard")
    } catch (error) {
      toast.error("Failed to copy link")
    }
  }

  const sendEmail = () => {
    if (!email) {
      toast.error("Please enter an email address")
      return
    }

    // In a real implementation, this would call an API endpoint
    // For now, we'll use mailto
    const subject = encodeURIComponent(`Document: ${documentTitle}`)
    const body = encodeURIComponent(`You can view the document here: ${shareUrl}`)
    window.location.href = `mailto:${email}?subject=${subject}&body=${body}`
    
    toast.success("Email client opened")
    setEmail("")
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Share Document</DialogTitle>
          <DialogDescription>
            Share "{documentTitle}" with others
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="link" className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="link">Copy Link</TabsTrigger>
            <TabsTrigger value="email">Send Email</TabsTrigger>
          </TabsList>

          <TabsContent value="link" className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="share-link">Document Link</Label>
              <div className="flex gap-2">
                <Input
                  id="share-link"
                  value={shareUrl}
                  readOnly
                  className="flex-1"
                />
                <Button
                  size="icon"
                  variant="outline"
                  onClick={copyToClipboard}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <p className="text-sm text-muted-foreground">
              Anyone with this link can view the document preview
            </p>
          </TabsContent>

          <TabsContent value="email" className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email Address</Label>
              <Input
                id="email"
                type="email"
                placeholder="Enter email address"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    sendEmail()
                  }
                }}
              />
            </div>
            <Button
              className="w-full"
              onClick={sendEmail}
              disabled={!email}
            >
              <Mail className="mr-2 h-4 w-4" />
              Send Email
            </Button>
            <p className="text-sm text-muted-foreground">
              This will open your default email client with a link to the document
            </p>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}