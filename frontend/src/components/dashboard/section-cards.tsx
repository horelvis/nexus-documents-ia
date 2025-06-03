"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileText, Upload, Search, MessageSquare, TrendingUp, TrendingDown } from "lucide-react";
import { useDocuments } from "@/hooks/use-api";

export function SectionCards() {
  const { documents } = useDocuments();
  
  const totalDocuments = documents.length;
  const totalSize = documents.reduce((acc, doc) => acc + doc.file_size, 0);
  const indexedDocuments = documents.filter(doc => doc.indexed === 'indexed').length;
  const indexingProgress = totalDocuments > 0 ? (indexedDocuments / totalDocuments) * 100 : 0;

  const cards = [
    {
      title: "Total Documents",
      value: totalDocuments.toString(),
      description: "Documents in your library",
      icon: FileText,
      trend: totalDocuments > 0 ? "+12.5%" : "0%",
      trendUp: true,
    },
    {
      title: "Storage Used", 
      value: `${(totalSize / (1024 * 1024)).toFixed(1)} MB`,
      description: "Total file size",
      icon: Upload,
      trend: "+2.1%",
      trendUp: true,
    },
    {
      title: "Indexed Documents",
      value: indexedDocuments.toString(),
      description: `${indexingProgress.toFixed(0)}% of total`,
      icon: Search,
      trend: `${indexingProgress.toFixed(0)}%`,
      trendUp: indexingProgress > 80,
    },
    {
      title: "Chat Sessions",
      value: "0",
      description: "Active conversations",
      icon: MessageSquare,
      trend: "0%",
      trendUp: false,
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 px-4 lg:px-6 md:grid-cols-2 lg:grid-cols-4">
      {cards.map((card, index) => {
        const Icon = card.icon;
        const TrendIcon = card.trendUp ? TrendingUp : TrendingDown;
        
        return (
          <Card key={index}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardDescription className="text-sm font-medium">
                {card.title}
              </CardDescription>
              <Icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{card.value}</div>
              <div className="flex items-center justify-between mt-2">
                <p className="text-xs text-muted-foreground">
                  {card.description}
                </p>
                <div className="flex items-center space-x-1">
                  <Badge 
                    variant="outline" 
                    className={`text-xs ${card.trendUp ? 'text-green-600' : 'text-red-600'}`}
                  >
                    <TrendIcon className="h-3 w-3 mr-1" />
                    {card.trend}
                  </Badge>
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}