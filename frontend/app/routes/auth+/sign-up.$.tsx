import { SignUp } from "@clerk/remix";

export default function SignUpPage() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
      <SignUp routing="path" path="/auth/sign-up" signInUrl="/auth/sign-in" redirectUrl="/dashboard" />
    </div>
  );
}
