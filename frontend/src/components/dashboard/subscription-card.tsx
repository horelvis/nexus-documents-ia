"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useSubscription } from "@/hooks/use-subscription";
import { CreditCard, Calendar, AlertCircle, ExternalLink } from "lucide-react";
import Link from "next/link";

export function SubscriptionCard() {
  const { subscription, loading, openCustomerPortal } = useSubscription();

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Subscription</CardTitle>
          <CardDescription>Manage your subscription plan</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-1/4"></div>
            <div className="h-4 bg-gray-200 rounded w-1/2"></div>
            <div className="h-8 bg-gray-200 rounded w-full"></div>
          </div>
        </CardContent>
      </Card>
    );
  }

  const isFreePlan = !subscription || subscription.id === 'free';
  const planName = isFreePlan ? 'Free' : subscription.plan_id;
  const planStatus = isFreePlan ? 'active' : subscription.status;

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-green-100 text-green-800';
      case 'past_due':
        return 'bg-yellow-100 text-yellow-800';
      case 'unpaid':
      case 'canceled':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleDateString();
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <CreditCard className="h-5 w-5" />
              Subscription
            </CardTitle>
            <CardDescription>Manage your subscription plan</CardDescription>
          </div>
          <Badge className={getStatusColor(planStatus)}>
            {planStatus}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Current Plan</span>
            <span className="text-sm text-muted-foreground capitalize">
              {planName}
            </span>
          </div>
          
          {!isFreePlan && subscription && (
            <>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Billing Cycle</span>
                <span className="text-sm text-muted-foreground capitalize">
                  {subscription.interval}ly
                </span>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Next Billing Date</span>
                <span className="text-sm text-muted-foreground">
                  <Calendar className="inline h-3 w-3 mr-1" />
                  {formatDate(subscription.current_period_end)}
                </span>
              </div>

              {subscription.cancel_at_period_end && (
                <div className="flex items-center gap-2 p-3 bg-yellow-50 rounded-lg">
                  <AlertCircle className="h-4 w-4 text-yellow-600" />
                  <span className="text-sm text-yellow-800">
                    Your subscription will be cancelled at the end of the current billing period.
                  </span>
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex flex-col sm:flex-row gap-2">
          {isFreePlan ? (
            <Button asChild className="flex-1">
              <Link href="/pricing">
                <ExternalLink className="h-4 w-4 mr-2" />
                Upgrade Plan
              </Link>
            </Button>
          ) : (
            <Button 
              variant="outline" 
              onClick={openCustomerPortal}
              className="flex-1"
            >
              <ExternalLink className="h-4 w-4 mr-2" />
              Manage Subscription
            </Button>
          )}
          
          <Button variant="outline" asChild>
            <Link href="/pricing">
              View All Plans
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}