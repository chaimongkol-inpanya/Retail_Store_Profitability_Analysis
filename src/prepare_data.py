from src.pipeline import RetailPipeline
from src.thailand import ThailandMockGenerator

if __name__ == "__main__":
    ThailandMockGenerator().generate()
    RetailPipeline().run()
