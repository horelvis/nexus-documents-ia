"use client"

import { motion } from "framer-motion"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { File, ExternalLink, Calendar, User } from "lucide-react"
import { cn } from "@/lib/utils"

interface DocumentInfo {
  name: string
  id?: string
  url?: string
  previewUrl?: string
  collection?: string
  createdAt?: string
  author?: string
  fileType?: string
  relevanceScore?: number
}

interface DocumentDisplayProps {
  documents: DocumentInfo[]
  onDocumentClick?: (doc: DocumentInfo) => void
  onPreviewClick?: (doc: DocumentInfo) => void
  className?: string
}

export function DocumentDisplay({ 
  documents, 
  onDocumentClick, 
  onPreviewClick, 
  className 
}: DocumentDisplayProps) {
  if (!documents || documents.length === 0) return null

  return (
    <motion.div
      className={cn("w-full flex flex-col gap-3", className)}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", damping: 20, stiffness: 300 }}
    >
      {documents.map((doc, index) => (
        <motion.div
          key={doc.id || doc.name || index}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: index * 0.05 }}
        >
          <Card 
            className={cn(
              "hover:shadow-md transition-all duration-200 cursor-pointer",
              "border-l-4 border-l-blue-500"
            )}
            onClick={() => onDocumentClick?.(doc)}
          >
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <File className="h-4 w-4 text-blue-500" />
                  <CardTitle className="text-sm font-medium line-clamp-1">
                    {doc.name}
                  </CardTitle>
                </div>
                {doc.relevanceScore && (
                  <Badge variant="secondary" className="text-xs">
                    {Math.round(doc.relevanceScore * 100)}%
                  </Badge>
                )}
              </div>
              
              {(doc.collection || doc.fileType) && (
                <CardDescription className="text-xs flex items-center gap-2">
                  {doc.collection && <span>{doc.collection}</span>}
                  {doc.fileType && (
                    <Badge variant="outline" className="text-xs px-1.5 py-0">
                      {doc.fileType.toUpperCase()}
                    </Badge>
                  )}
                </CardDescription>
              )}
            </CardHeader>

            <CardContent className="pt-0">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4 text-xs text-muted-foreground">
                  {doc.createdAt && (
                    <div className="flex items-center gap-1">
                      <Calendar className="h-3 w-3" />
                      <span>{doc.createdAt}</span>
                    </div>
                  )}
                  {doc.author && (
                    <div className="flex items-center gap-1">
                      <User className="h-3 w-3" />
                      <span>{doc.author}</span>
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-1">
                  {doc.previewUrl && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 px-2 text-xs"
                      onClick={(e) => {
                        e.stopPropagation()
                        onPreviewClick?.(doc)
                      }}
                    >
                      <ExternalLink className="h-3 w-3 mr-1" />
                      Vista previa
                    </Button>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      ))}
    </motion.div>
  )
}