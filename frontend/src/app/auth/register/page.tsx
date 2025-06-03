import { SignUp } from "@clerk/nextjs";

const Register = () => {
    return (
        <div className="flex min-h-screen items-center justify-center bg-gray-50">
            <div className="w-full max-w-md">
                <div className="text-center mb-8">
                    <h1 className="text-3xl font-bold text-gray-900">Create account</h1>
                    <p className="text-gray-600 mt-2">Get started with document management</p>
                </div>
                <SignUp 
                    appearance={{
                        elements: {
                            formButtonPrimary: 
                                "bg-blue-600 hover:bg-blue-700 text-sm normal-case",
                            card: "shadow-lg border-0",
                        },
                    }}
                />
            </div>
        </div>
    );
};

export default Register;
