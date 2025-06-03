"use client";

import { useCurrentUser } from "@/hooks/use-api";
import { UserButton } from "@clerk/nextjs";
import { useUser, useAuth } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { 
  Upload, 
  Search, 
  MessageSquare, 
  RefreshCw, 
  AlertCircle, 
  Wifi, 
  WifiOff,
  TrendingUp,
  Users,
  FileText,
  BarChart3,
  Activity,
  Download,
  Eye,
  Plus
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { OnboardingModal } from "@/components/onboarding/onboarding-modal";
import { useDocuments } from "@/hooks/use-api";

const Dashboard = () => {
    const { isLoaded, isSignedIn } = useAuth();
    const { user: clerkUser } = useUser();
    const { user: backendUser, loading: userLoading, error: backendError } = useCurrentUser();
    const { uploadDocument } = useDocuments();
    const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [retrying, setRetrying] = useState(false);

    const handleRetry = async () => {
        setRetrying(true);
        // Force a refetch by reloading the page or triggering the hook again
        setTimeout(() => {
            window.location.reload();
        }, 1000);
    };

    const handleFileUpload = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const formData = new FormData(event.currentTarget);
        const file = formData.get('file') as File;
        const title = formData.get('title') as string;
        const description = formData.get('description') as string;

        if (!file || !title) {
            toast.error('Please select a file and enter a title');
            return;
        }

        try {
            setUploading(true);
            await uploadDocument(file, { title, description });
            setUploadDialogOpen(false);
            event.currentTarget.reset();
        } catch (error) {
            console.error('Upload failed:', error);
        } finally {
            setUploading(false);
        }
    };

    // Check Clerk authentication first
    if (!isLoaded) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary mx-auto"></div>
                    <p className="mt-4 text-muted-foreground">Loading...</p>
                </div>
            </div>
        );
    }

    if (!isSignedIn) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="text-center">
                    <div className="mb-4">
                        <AlertCircle className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
                    </div>
                    <h2 className="text-2xl font-semibold mb-2">Authentication Required</h2>
                    <p className="text-muted-foreground mb-6">Please sign in to access your dashboard</p>
                    <Button asChild>
                        <a href="/auth/login">Sign In</a>
                    </Button>
                </div>
            </div>
        );
    }

    // If Clerk user exists but backend connection fails, show a functional dashboard with limited features
    if (!userLoading && (!backendUser || backendError)) {
        return (
            <div className="flex-col md:flex">
                <div className="border-b">
                    <div className="flex h-16 items-center px-4">
                        <div className="flex items-center space-x-4">
                            <h2 className="text-lg font-semibold">Dashboard</h2>
                        </div>
                        <div className="ml-auto flex items-center space-x-4">
                            <span className="text-sm text-muted-foreground">
                                Welcome back, {clerkUser?.fullName || clerkUser?.firstName || "User"}
                            </span>
                            <UserButton />
                        </div>
                    </div>
                </div>

                {/* Connection Error Banner */}
                <div className="bg-orange-50 border-l-4 border-orange-400 p-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center">
                            <WifiOff className="h-5 w-5 text-orange-400 mr-3" />
                            <div>
                                <p className="text-orange-700 font-medium">Limited Connectivity</p>
                                <p className="text-orange-600 text-sm">
                                    Unable to connect to our servers. Some features may be unavailable.
                                </p>
                            </div>
                        </div>
                        <Button 
                            variant="outline" 
                            size="sm" 
                            onClick={handleRetry}
                            disabled={retrying}
                        >
                            {retrying ? (
                                <>
                                    <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                                    Retrying...
                                </>
                            ) : (
                                <>
                                    <RefreshCw className="mr-2 h-4 w-4" />
                                    Retry
                                </>
                            )}
                        </Button>
                    </div>
                </div>

                <div className="flex-1 space-y-4 p-8 pt-6">
                    <div className="flex items-center justify-between space-y-2">
                        <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
                        <div className="flex items-center space-x-2">
                            <Button disabled variant="outline">
                                <Plus className="mr-2 h-4 w-4" />
                                Upload Document
                            </Button>
                        </div>
                    </div>
                    
                    <Tabs defaultValue="overview" className="space-y-4">
                        <TabsList>
                            <TabsTrigger value="overview">Overview</TabsTrigger>
                            <TabsTrigger value="status">Connection Status</TabsTrigger>
                            <TabsTrigger value="help" disabled>Documents</TabsTrigger>
                            <TabsTrigger value="help" disabled>Analytics</TabsTrigger>
                        </TabsList>
                        <TabsContent value="overview" className="space-y-4">
                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                                <Card>
                                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                        <CardTitle className="text-sm font-medium">
                                            Connection Status
                                        </CardTitle>
                                        <WifiOff className="h-4 w-4 text-orange-500" />
                                    </CardHeader>
                                    <CardContent>
                                        <div className="text-2xl font-bold text-orange-500">Offline</div>
                                        <p className="text-xs text-muted-foreground">
                                            Unable to reach servers
                                        </p>
                                    </CardContent>
                                </Card>
                                <Card>
                                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                        <CardTitle className="text-sm font-medium">
                                            Account Status
                                        </CardTitle>
                                        <Users className="h-4 w-4 text-green-500" />
                                    </CardHeader>
                                    <CardContent>
                                        <div className="text-2xl font-bold text-green-500">Active</div>
                                        <p className="text-xs text-muted-foreground">
                                            Authentication verified
                                        </p>
                                    </CardContent>
                                </Card>
                                <Card>
                                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                        <CardTitle className="text-sm font-medium">
                                            Data Security
                                        </CardTitle>
                                        <FileText className="h-4 w-4 text-green-500" />
                                    </CardHeader>
                                    <CardContent>
                                        <div className="text-2xl font-bold text-green-500">Safe</div>
                                        <p className="text-xs text-muted-foreground">
                                            All data preserved
                                        </p>
                                    </CardContent>
                                </Card>
                                <Card>
                                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                        <CardTitle className="text-sm font-medium">
                                            Service Recovery
                                        </CardTitle>
                                        <Activity className="h-4 w-4 text-blue-500" />
                                    </CardHeader>
                                    <CardContent>
                                        <div className="text-2xl font-bold text-blue-500">Auto</div>
                                        <p className="text-xs text-muted-foreground">
                                            Reconnecting...
                                        </p>
                                    </CardContent>
                                </Card>
                            </div>
                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                                <Card className="col-span-4">
                                    <CardHeader>
                                        <CardTitle>Service Status</CardTitle>
                                        <CardDescription>Current connectivity information</CardDescription>
                                    </CardHeader>
                                    <CardContent className="pl-2">
                                        <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                                            <div className="text-center">
                                                <WifiOff className="h-16 w-16 mx-auto mb-4 text-orange-500 opacity-75" />
                                                <p className="text-lg font-medium mb-2">Connection Unavailable</p>
                                                <p className="text-sm mb-4">We're working to restore full functionality</p>
                                                <Button onClick={handleRetry} disabled={retrying} variant="outline">
                                                    {retrying ? (
                                                        <>
                                                            <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                                                            Retrying...
                                                        </>
                                                    ) : (
                                                        <>
                                                            <RefreshCw className="mr-2 h-4 w-4" />
                                                            Try Again
                                                        </>
                                                    )}
                                                </Button>
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                                <Card className="col-span-3">
                                    <CardHeader>
                                        <CardTitle>What You Can Do</CardTitle>
                                        <CardDescription>
                                            Available actions during connectivity issues
                                        </CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="space-y-4">
                                            {[
                                                { 
                                                    icon: RefreshCw, 
                                                    title: "Try Again", 
                                                    desc: "Use the retry button to reconnect",
                                                    color: "text-blue-500"
                                                },
                                                { 
                                                    icon: Wifi, 
                                                    title: "Check Network", 
                                                    desc: "Verify your internet connection",
                                                    color: "text-green-500"
                                                },
                                                { 
                                                    icon: AlertCircle, 
                                                    title: "Wait a Moment", 
                                                    desc: "Services will restore automatically",
                                                    color: "text-orange-500"
                                                },
                                                { 
                                                    icon: MessageSquare, 
                                                    title: "Contact Support", 
                                                    desc: "If issues persist for too long",
                                                    color: "text-purple-500"
                                                }
                                            ].map((item, index) => (
                                                <div key={index} className="flex items-start space-x-3">
                                                    <item.icon className={`h-5 w-5 mt-0.5 ${item.color}`} />
                                                    <div className="space-y-1">
                                                        <p className="text-sm font-medium leading-none">{item.title}</p>
                                                        <p className="text-sm text-muted-foreground">{item.desc}</p>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </CardContent>
                                </Card>
                            </div>
                        </TabsContent>
                        <TabsContent value="status" className="space-y-4">
                            <Card>
                                <CardHeader>
                                    <CardTitle>Connection Diagnostics</CardTitle>
                                    <CardDescription>
                                        Detailed information about current connectivity
                                    </CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <div className="space-y-6">
                                        <div className="flex items-center justify-between p-4 border rounded-lg">
                                            <div className="flex items-center space-x-3">
                                                <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                                                <div>
                                                    <p className="font-medium">Client Authentication</p>
                                                    <p className="text-sm text-muted-foreground">Successfully authenticated with Clerk</p>
                                                </div>
                                            </div>
                                            <Wifi className="h-5 w-5 text-green-500" />
                                        </div>
                                        
                                        <div className="flex items-center justify-between p-4 border rounded-lg">
                                            <div className="flex items-center space-x-3">
                                                <div className="w-3 h-3 bg-orange-500 rounded-full"></div>
                                                <div>
                                                    <p className="font-medium">Backend Connection</p>
                                                    <p className="text-sm text-muted-foreground">Unable to reach document services</p>
                                                </div>
                                            </div>
                                            <WifiOff className="h-5 w-5 text-orange-500" />
                                        </div>
                                        
                                        <div className="flex items-center justify-between p-4 border rounded-lg">
                                            <div className="flex items-center space-x-3">
                                                <div className="w-3 h-3 bg-blue-500 rounded-full animate-pulse"></div>
                                                <div>
                                                    <p className="font-medium">Auto Recovery</p>
                                                    <p className="text-sm text-muted-foreground">Attempting to reconnect automatically</p>
                                                </div>
                                            </div>
                                            <RefreshCw className="h-5 w-5 text-blue-500 animate-spin" />
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        </TabsContent>
                    </Tabs>
                </div>
            </div>
        );
    }

    // Show loading state while backend user loads
    if (userLoading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary mx-auto"></div>
                    <p className="mt-4 text-muted-foreground">Setting up your dashboard...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="flex-col md:flex">
            <div className="border-b">
                <div className="flex h-16 items-center px-4">
                    <div className="flex items-center space-x-4">
                        <h2 className="text-lg font-semibold">Dashboard</h2>
                    </div>
                    <div className="ml-auto flex items-center space-x-4">
                        <span className="text-sm text-muted-foreground">
                            Welcome back, {backendUser?.full_name || clerkUser?.fullName || clerkUser?.firstName || "User"}
                        </span>
                        <UserButton />
                    </div>
                </div>
            </div>
            <div className="flex-1 space-y-4 p-8 pt-6">
                <div className="flex items-center justify-between space-y-2">
                    <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
                    <div className="flex items-center space-x-2">
                        <Dialog open={uploadDialogOpen} onOpenChange={setUploadDialogOpen}>
                            <DialogTrigger asChild>
                                <Button>
                                    <Plus className="mr-2 h-4 w-4" />
                                    Upload Document
                                </Button>
                            </DialogTrigger>
                            <DialogContent>
                                <DialogHeader>
                                    <DialogTitle>Upload Document</DialogTitle>
                                    <DialogDescription>
                                        Upload a new document to your library
                                    </DialogDescription>
                                </DialogHeader>
                                <form onSubmit={handleFileUpload} className="space-y-4">
                                    <div>
                                        <Label htmlFor="file">File</Label>
                                        <Input 
                                            id="file" 
                                            name="file" 
                                            type="file" 
                                            accept=".pdf,.doc,.docx,.txt,.md"
                                            required
                                        />
                                    </div>
                                    <div>
                                        <Label htmlFor="title">Title</Label>
                                        <Input 
                                            id="title" 
                                            name="title" 
                                            placeholder="Document title"
                                            required
                                        />
                                    </div>
                                    <div>
                                        <Label htmlFor="description">Description (optional)</Label>
                                        <Input 
                                            id="description" 
                                            name="description" 
                                            placeholder="Brief description"
                                        />
                                    </div>
                                    <Button type="submit" disabled={uploading} className="w-full">
                                        {uploading ? 'Uploading...' : 'Upload'}
                                    </Button>
                                </form>
                            </DialogContent>
                        </Dialog>
                    </div>
                </div>
                <Tabs defaultValue="overview" className="space-y-4">
                    <TabsList>
                        <TabsTrigger value="overview">Overview</TabsTrigger>
                        <TabsTrigger value="analytics">Analytics</TabsTrigger>
                        <TabsTrigger value="documents">Documents</TabsTrigger>
                        <TabsTrigger value="notifications">Notifications</TabsTrigger>
                    </TabsList>
                    <TabsContent value="overview" className="space-y-4">
                        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                    <CardTitle className="text-sm font-medium">
                                        Total Documents
                                    </CardTitle>
                                    <FileText className="h-4 w-4 text-muted-foreground" />
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-bold">254</div>
                                    <p className="text-xs text-muted-foreground">
                                        +20.1% from last month
                                    </p>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                    <CardTitle className="text-sm font-medium">
                                        Storage Used
                                    </CardTitle>
                                    <BarChart3 className="h-4 w-4 text-muted-foreground" />
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-bold">12.3 GB</div>
                                    <p className="text-xs text-muted-foreground">
                                        +15% from last month
                                    </p>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                    <CardTitle className="text-sm font-medium">
                                        Document Views
                                    </CardTitle>
                                    <Eye className="h-4 w-4 text-muted-foreground" />
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-bold">3,847</div>
                                    <p className="text-xs text-muted-foreground">
                                        +8.1% from last month
                                    </p>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                    <CardTitle className="text-sm font-medium">
                                        AI Insights
                                    </CardTitle>
                                    <TrendingUp className="h-4 w-4 text-muted-foreground" />
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-bold">127</div>
                                    <p className="text-xs text-muted-foreground">
                                        +12.5% from last month
                                    </p>
                                </CardContent>
                            </Card>
                        </div>
                        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                            <Card className="col-span-4">
                                <CardHeader>
                                    <CardTitle>Document Activity</CardTitle>
                                </CardHeader>
                                <CardContent className="pl-2">
                                    <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                                        <div className="text-center">
                                            <Activity className="h-12 w-12 mx-auto mb-4 opacity-50" />
                                            <p>Activity chart will be displayed here</p>
                                            <p className="text-sm">Uploads, views, and AI processing over time</p>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                            <Card className="col-span-3">
                                <CardHeader>
                                    <CardTitle>Recent Documents</CardTitle>
                                    <CardDescription>
                                        Your latest uploaded documents
                                    </CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <div className="space-y-4">
                                        {[
                                            { name: "Financial Report Q4.pdf", time: "2 hours ago", size: "2.4 MB" },
                                            { name: "Meeting Notes.docx", time: "4 hours ago", size: "145 KB" },
                                            { name: "Project Proposal.pdf", time: "1 day ago", size: "1.8 MB" },
                                            { name: "Technical Specs.md", time: "2 days ago", size: "67 KB" }
                                        ].map((doc, index) => (
                                            <div key={index} className="flex items-center">
                                                <FileText className="mr-2 h-4 w-4 text-muted-foreground" />
                                                <div className="ml-2 space-y-1">
                                                    <p className="text-sm font-medium leading-none">{doc.name}</p>
                                                    <p className="text-sm text-muted-foreground">
                                                        {doc.time} • {doc.size}
                                                    </p>
                                                </div>
                                                <div className="ml-auto font-medium">
                                                    <Button variant="ghost" size="sm">
                                                        <Eye className="h-4 w-4" />
                                                    </Button>
                                                    <Button variant="ghost" size="sm">
                                                        <Download className="h-4 w-4" />
                                                    </Button>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </CardContent>
                            </Card>
                        </div>
                    </TabsContent>
                    <TabsContent value="analytics" className="space-y-4">
                        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                    <CardTitle className="text-sm font-medium">
                                        Processing Time
                                    </CardTitle>
                                    <Activity className="h-4 w-4 text-muted-foreground" />
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-bold">2.4s</div>
                                    <p className="text-xs text-muted-foreground">
                                        Average processing time
                                    </p>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                    <CardTitle className="text-sm font-medium">
                                        Success Rate
                                    </CardTitle>
                                    <TrendingUp className="h-4 w-4 text-muted-foreground" />
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-bold">99.2%</div>
                                    <p className="text-xs text-muted-foreground">
                                        Document processing success
                                    </p>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                    <CardTitle className="text-sm font-medium">
                                        Search Queries
                                    </CardTitle>
                                    <Search className="h-4 w-4 text-muted-foreground" />
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-bold">1,247</div>
                                    <p className="text-xs text-muted-foreground">
                                        This month
                                    </p>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                    <CardTitle className="text-sm font-medium">
                                        Chat Sessions
                                    </CardTitle>
                                    <MessageSquare className="h-4 w-4 text-muted-foreground" />
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-bold">89</div>
                                    <p className="text-xs text-muted-foreground">
                                        AI conversations
                                    </p>
                                </CardContent>
                            </Card>
                        </div>
                    </TabsContent>
                    <TabsContent value="documents" className="space-y-4">
                        <Card>
                            <CardHeader>
                                <CardTitle>Document Library</CardTitle>
                                <CardDescription>
                                    Manage and organize your documents
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="text-center py-8">
                                    <FileText className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                                    <p className="text-muted-foreground">Document table will be displayed here</p>
                                </div>
                            </CardContent>
                        </Card>
                    </TabsContent>
                    <TabsContent value="notifications" className="space-y-4">
                        <Card>
                            <CardHeader>
                                <CardTitle>Notifications</CardTitle>
                                <CardDescription>
                                    Recent system notifications and updates
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="text-center py-8">
                                    <AlertCircle className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                                    <p className="text-muted-foreground">No new notifications</p>
                                </div>
                            </CardContent>
                        </Card>
                    </TabsContent>
                </Tabs>
            </div>
            
            {/* Onboarding Modal */}
            <OnboardingModal />
        </div>
    );
};

export default Dashboard;