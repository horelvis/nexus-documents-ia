import React from 'react'

const SectionContainer = ({ children }: { children: React.ReactNode }) => {
    return (
        <main id='background' className="flex-none min-h-screen -z-10">
            <div className="fixed inset-0 bg-black hidden lg:flex"></div>

            <div className="absolute top-[-266px] left-[calc(55%-379px/2)] bg-primary/60 opacity-50 rounded-full blur-[10rem] w-[379px] h-[620px] hidden lg:flex"></div>

            <div className="absolute top-[-60px] left-[calc(50%-433px/2)] bg-primaryLight/40 opacity-50 rounded-full blur-[15rem] w-[433px] h-[525px] hidden lg:flex"></div>

            {children}
        </main>
    )
};

export default SectionContainer