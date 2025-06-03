"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FileText, Search, MoreHorizontal, Download, Trash2 } from "lucide-react";
import { useDocuments } from "@/hooks/use-api";
import { useState } from "react";
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from "@/components/ui/dropdown-menu";

export function DataTable() {
  const { documents, loading } = useDocuments();
  const [searchTerm, setSearchTerm] = useState("");

  const filteredDocuments = documents.filter(doc =>
    doc.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    doc.filename.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Recent Documents</CardTitle>
          <CardDescription>
            Your recently uploaded documents
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="flex items-center space-x-4 animate-pulse">
                <div className="h-4 w-4 bg-gray-200 rounded"></div>
                <div className="h-4 bg-gray-200 rounded flex-1"></div>
                <div className="h-4 w-16 bg-gray-200 rounded"></div>
                <div className="h-4 w-20 bg-gray-200 rounded"></div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Recent Documents</CardTitle>
            <CardDescription>
              Your recently uploaded documents
            </CardDescription>
          </div>
          <div className="flex items-center space-x-2">
            <div className="relative">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search documents..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-8 w-64"
              />
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {filteredDocuments.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <FileText className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium text-foreground mb-2">
              {searchTerm ? "No documents found" : "No documents yet"}
            </h3>
            <p className="text-muted-foreground">
              {searchTerm 
                ? "Try adjusting your search terms"
                : "Upload your first document to get started"}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Table Header */}
            <div className="grid grid-cols-12 gap-4 text-sm font-medium text-muted-foreground border-b pb-2">
              <div className="col-span-4">Document</div>
              <div className="col-span-2">Status</div>
              <div className="col-span-2">Size</div>
              <div className="col-span-2">Date</div>
              <div className="col-span-1">Tags</div>
              <div className="col-span-1"></div>
            </div>
            
            {/* Table Rows */}
            {filteredDocuments.slice(0, 10).map((doc) => (
              <div key={doc.id} className="grid grid-cols-12 gap-4 items-center py-3 border-b last:border-b-0 hover:bg-muted/50 transition-colors">
                <div className="col-span-4">
                  <div className="flex items-center space-x-3">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="font-medium text-sm truncate">{doc.title}</p>
                      <p className="text-xs text-muted-foreground truncate">{doc.filename}</p>
                    </div>
                  </div>
                </div>
                
                <div className="col-span-2">
                  <Badge 
                    variant={doc.indexed === 'indexed' ? 'default' : 'secondary'}
                    className="text-xs"
                  >
                    {doc.indexed === 'indexed' ? 'Indexed' : 'Processing'}
                  </Badge>
                </div>
                
                <div className="col-span-2">
                  <span className="text-sm text-muted-foreground">
                    {(doc.file_size / 1024).toFixed(1)} KB
                  </span>
                </div>
                
                <div className="col-span-2">
                  <span className="text-sm text-muted-foreground">
                    {new Date(doc.created_at).toLocaleDateString()}
                  </span>
                </div>
                
                <div className="col-span-1">
                  {doc.tags.length > 0 && (
                    <Badge variant="outline" className="text-xs">
                      +{doc.tags.length}
                    </Badge>
                  )}
                </div>
                
                <div className="col-span-1">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem>
                        <Download className="mr-2 h-4 w-4" />
                        Download
                      </DropdownMenuItem>
                      <DropdownMenuItem className="text-red-600">
                        <Trash2 className="mr-2 h-4 w-4" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>
            ))}
          </div>
        )}
        
        {filteredDocuments.length > 10 && (
          <div className="flex justify-center mt-4">
            <Button variant="outline" size="sm">
              View All Documents
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}