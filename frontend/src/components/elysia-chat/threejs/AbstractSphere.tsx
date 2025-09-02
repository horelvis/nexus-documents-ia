// AbstractSphere - Adapted from https://github.com/weaviate/elysia-frontend

import React, { useEffect, useRef, useContext } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import vertex from "./vertex.glsl";
import fragment from "./fragment.glsl";
import { useGlobeSettings } from "@/hooks/useGlobeSettings";
import { ToastContext } from "@/contexts/ToastContext";
import { GlobeSettings, DEFAULT_GLOBE_SETTINGS } from "./globeConfig";

function BasicSphere({
  displacementStrength,
  distortionStrength,
  settings,
  ...props
}: {
  displacementStrength: React.MutableRefObject<number> | null;
  distortionStrength: React.MutableRefObject<number> | null;
  settings: GlobeSettings;
  /* eslint-disable @typescript-eslint/no-explicit-any */
} & any) {
  const meshRef = useRef<THREE.Mesh>();
  /* eslint-disable @typescript-eslint/no-explicit-any */
  const materialRef = useRef<any>();

  const uniformsRef = useRef({
    uTime: { value: 0 },
    uTimeFrequency: {
      value: (settings || DEFAULT_GLOBE_SETTINGS).timeFrequency,
    },
    uDistortionFrequency: {
      value: (settings || DEFAULT_GLOBE_SETTINGS).distortionFrequency,
    },
    uDistortionStrength: {
      value: (settings || DEFAULT_GLOBE_SETTINGS).distortionStrength,
    },
    uDisplacementFrequency: {
      value: (settings || DEFAULT_GLOBE_SETTINGS).displacementFrequency,
    },
    uDisplacementStrength: {
      value: (settings || DEFAULT_GLOBE_SETTINGS).displacementStrength,
    },
    uLightAColor: {
      value: new THREE.Color((settings || DEFAULT_GLOBE_SETTINGS).lightAColor),
    },
    uLightBColor: {
      value: new THREE.Color((settings || DEFAULT_GLOBE_SETTINGS).lightBColor),
    },
    uLightAPosition: {
      value: new THREE.Vector3(
        ...(settings || DEFAULT_GLOBE_SETTINGS).lightAPosition
      ),
    },
    uLightBPosition: {
      value: new THREE.Vector3(
        ...(settings || DEFAULT_GLOBE_SETTINGS).lightBPosition
      ),
    },
    uLightAIntensity: {
      value: (settings || DEFAULT_GLOBE_SETTINGS).lightAIntensity,
    },
    uLightBIntensity: {
      value: (settings || DEFAULT_GLOBE_SETTINGS).lightBIntensity,
    },
    uSubdivision: {
      value: new THREE.Vector2(
        (settings || DEFAULT_GLOBE_SETTINGS).subdivisionX,
        (settings || DEFAULT_GLOBE_SETTINGS).subdivisionY
      ),
    },
    uFresnelOffset: {
      value: (settings || DEFAULT_GLOBE_SETTINGS).fresnelOffset,
    },
    uFresnelMultiplier: {
      value: (settings || DEFAULT_GLOBE_SETTINGS).fresnelMultiplier,
    },
    uFresnelPower: { value: (settings || DEFAULT_GLOBE_SETTINGS).fresnelPower },
    uNoiseStrength: {
      value: (settings || DEFAULT_GLOBE_SETTINGS).noiseStrength,
    },
    uNoiseFrequency: {
      value: (settings || DEFAULT_GLOBE_SETTINGS).noiseFrequency,
    },
  });

  // Update uniforms when settings change
  useEffect(() => {
    const currentSettings = settings || DEFAULT_GLOBE_SETTINGS;

    uniformsRef.current.uTimeFrequency.value = currentSettings.timeFrequency;
    uniformsRef.current.uDistortionFrequency.value =
      currentSettings.distortionFrequency;
    uniformsRef.current.uDistortionStrength.value =
      currentSettings.distortionStrength;
    uniformsRef.current.uDisplacementFrequency.value =
      currentSettings.displacementFrequency;
    uniformsRef.current.uDisplacementStrength.value =
      currentSettings.displacementStrength;
    uniformsRef.current.uLightAColor.value = new THREE.Color(
      currentSettings.lightAColor
    );
    uniformsRef.current.uLightBColor.value = new THREE.Color(
      currentSettings.lightBColor
    );
    uniformsRef.current.uLightAPosition.value = new THREE.Vector3(
      ...currentSettings.lightAPosition
    );
    uniformsRef.current.uLightBPosition.value = new THREE.Vector3(
      ...currentSettings.lightBPosition
    );
    uniformsRef.current.uLightAIntensity.value =
      currentSettings.lightAIntensity;
    uniformsRef.current.uLightBIntensity.value =
      currentSettings.lightBIntensity;
    uniformsRef.current.uSubdivision.value = new THREE.Vector2(
      currentSettings.subdivisionX,
      currentSettings.subdivisionY
    );
    uniformsRef.current.uFresnelOffset.value = currentSettings.fresnelOffset;
    uniformsRef.current.uFresnelMultiplier.value = Math.min(
      uniformsRef.current.uFresnelMultiplier.value + 0.01,
      currentSettings.fresnelMultiplier
    );
    uniformsRef.current.uFresnelPower.value = currentSettings.fresnelPower;
    uniformsRef.current.uNoiseStrength.value = currentSettings.noiseStrength;
    uniformsRef.current.uNoiseFrequency.value = currentSettings.noiseFrequency;
  }, [settings]);

  useFrame(({ clock }) => {
    const time = clock.getElapsedTime();
    if (materialRef.current) {
      uniformsRef.current.uTime.value = time;

      const currentSettings = settings || DEFAULT_GLOBE_SETTINGS;
      // Smoothly animate to the target fresnel multiplier from settings
      uniformsRef.current.uFresnelMultiplier.value += 0.01;
      uniformsRef.current.uFresnelMultiplier.value = Math.min(
        uniformsRef.current.uFresnelMultiplier.value,
        currentSettings.fresnelMultiplier || 1.0
      );

      if (
        displacementStrength &&
        displacementStrength.current > currentSettings.displacementStrength
      ) {
        const targetDisplacement = displacementStrength.current;
        const currentDisplacement =
          uniformsRef.current.uDisplacementStrength.value;
        const factor = 0.1;

        uniformsRef.current.uDisplacementStrength.value =
          THREE.MathUtils.lerp(
            currentDisplacement,
            targetDisplacement,
            factor
          );

        displacementStrength.current -= 0.0001;
        displacementStrength.current = Math.max(
          displacementStrength.current,
          currentSettings.displacementStrength
        );
      } else {
        // Return to settings value when not actively displacing
        uniformsRef.current.uDisplacementStrength.value =
          THREE.MathUtils.lerp(
            uniformsRef.current.uDisplacementStrength.value,
            currentSettings.displacementStrength,
            0.05
          );
      }

      if (
        distortionStrength &&
        distortionStrength.current > currentSettings.distortionStrength
      ) {
        const targetDistortion = distortionStrength.current;
        const currentDistortion =
          uniformsRef.current.uDistortionStrength.value;
        const factor = 0.1;

        uniformsRef.current.uDistortionStrength.value = THREE.MathUtils.lerp(
          currentDistortion,
          targetDistortion,
          factor
        );
        distortionStrength.current -= 0.0001;
        distortionStrength.current = Math.max(
          distortionStrength.current,
          currentSettings.distortionStrength
        );
      } else {
        // Return to settings value when not actively distorting
        uniformsRef.current.uDistortionStrength.value = THREE.MathUtils.lerp(
          uniformsRef.current.uDistortionStrength.value,
          currentSettings.distortionStrength,
          0.05
        );
      }
    }
  });

  return (
    <mesh ref={meshRef} scale={[1, 1, 1]} {...props}>
      {/* Using sphereGeometry with computed tangents */}
      <sphereGeometry
        args={[
          1,
          (settings || DEFAULT_GLOBE_SETTINGS).subdivisionX,
          (settings || DEFAULT_GLOBE_SETTINGS).subdivisionY,
        ]}
        onUpdate={(geometry) => {
          geometry.computeTangents();
        }}
      />
      <shaderMaterial
        ref={materialRef}
        vertexShader={vertex}
        fragmentShader={fragment}
        uniforms={uniformsRef.current}
        defines={{
          USE_TANGENT: "",
        }}
      />
    </mesh>
  );
}

function CameraRotation() {
  useFrame(({ camera }) => {
    // Rotate camera around the sphere
    const radius = 3.2; // Match the initial camera distance
    const speed = 0.1; // Adjust this value to control rotation speed
    const time = performance.now() * 0.001 * speed;

    camera.position.x = Math.sin(time) * radius;
    camera.position.z = Math.cos(time) * radius;
    camera.lookAt(0, 0, 0);
  });

  return null;
}

export default function AbstractSphere({
  displacementStrength,
  distortionStrength,
  className = "",
}: {
  displacementStrength?: React.MutableRefObject<number>;
  distortionStrength?: React.MutableRefObject<number>;
  className?: string;
}) {
  // Use the globe settings hook
  const {
    settings,
    hasUnsavedChanges,
    updateSetting,
    saveSettings,
    resetToDefaults,
    cancelChanges,
  } = useGlobeSettings();

  const { showSuccessToast, showErrorToast } = useContext(ToastContext);
  return (
    <div className={`w-full h-full ${className}`}>
      <Canvas
        camera={{ position: [0, 0, 3.2], fov: 45 }}
        style={{ background: "transparent" }}
        gl={{
          alpha: true,
          antialias: true,
        }}
      >
        <CameraRotation />
        <OrbitControls
          enableZoom={false}
          enablePan={false}
          enableRotate={false}
        />
        <BasicSphere
          dispose={null}
          displacementStrength={displacementStrength || null}
          distortionStrength={distortionStrength || null}
          settings={settings}
        />
      </Canvas>
    </div>
  );
}