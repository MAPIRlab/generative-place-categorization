from semantic.clustering_engine import ClusteringEngine
from semantic.dimensionality_reduction_engine import DimensionalityReductionEngine
import sys
from sklearn.preprocessing import StandardScaler
import argparse
import os
from typing import List


from embedding.bert_embedder import BERTEmbedder
from embedding.openai_embedder import OpenAIEmbedder
from embedding.roberta_embedder import RoBERTaEmbedder
from embedding.sentence_embedder import SentenceBERTEmbedder
from llm.large_language_model import LargeLanguageModel
from prompt.place_classifier_prompt import PlaceSegmenterPrompt
from semantic.semantic_descriptor_engine import SemanticDescriptorEngine
from utils import file_utils
import constants
import numpy as np

from voxeland.clustering import Clustering
from voxeland.cluster import Cluster
from voxeland.semantic_map import SemanticMap
from voxeland.semantic_map_object import SemanticMapObject

from tqdm import tqdm


from dotenv import load_dotenv
load_dotenv()


def get_results_path_for_method(args):
    base_path = os.path.join(constants.RESULTS_FOLDER_PATH, "method_results")
    method_specific_path = f"{args.method}"

    if args.method in (constants.METHOD_BERT_POST, constants.METHOD_DEEPSEEK_SBERT_POST):
        method_specific_path += f"_e{args.eps}_m{args.min_samples}_w{args.semantic_weight}_d{args.semantic_dimension}_mgt_{args.merge_geometric_threshold}_mst_{args.merge_semantic_threshold}_sst_{args.split_semantic_threshold}_r{args.dimensionality_reductor}_ca{args.clustering_algorithm}"
    elif args.method == constants.METHOD_GEOMETRIC:
        method_specific_path += f"_e{args.eps}_m{args.min_samples}_ca{args.clustering_algorithm}"
    elif args.method != constants.METHOD_DEEPSEEK:
        method_specific_path += f"_e{args.eps}_m{args.min_samples}_w{args.semantic_weight}_d{args.semantic_dimension}_r{args.dimensionality_reductor}_ca{args.clustering_algorithm}"

    return os.path.join(base_path, method_specific_path)


def get_geometric_descriptor(semantic_map_object: SemanticMapObject):
    return semantic_map_object.bbox_center


def main(args):

    # Instantiate models
    bert_embedder = BERTEmbedder()
    roberta_embedder = RoBERTaEmbedder()
    openai_embedder = OpenAIEmbedder()
    sbert_embedder = SentenceBERTEmbedder(
        model_id="sentence-transformers/all-mpnet-base-v2")
    deepseek_llm = LargeLanguageModel(model_id="deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
                                      cache_path=constants.LLM_CACHE_FILE_PATH)

    # Instantiate semantic descriptor engine
    semantic_descriptor_engine = SemanticDescriptorEngine(
        bert_embedder, roberta_embedder, openai_embedder, sbert_embedder, deepseek_llm
    )

    # Instantiate dimensionality reduction engine
    dim_reduction_engine = DimensionalityReductionEngine()

    # Load and pre-process semantic map
    semantic_maps: List[SemanticMap] = list()
    for semantic_map_file_name in sorted(os.listdir(constants.SEMANTIC_MAPS_FOLDER_PATH)):

        semantic_map_basename = file_utils.get_file_basename(
            semantic_map_file_name)
        # Load semantic map
        semantic_map_dict = file_utils.load_json(os.path.join(constants.SEMANTIC_MAPS_FOLDER_PATH,
                                                              semantic_map_file_name))
        # Create SemanticMap object
        semantic_maps.append(SemanticMap(semantic_map_basename,
                                         [SemanticMapObject(obj_id, obj_data) for obj_id, obj_data in semantic_map_dict["instances"].items()]))

    # For each semantic map
    for semantic_map in semantic_maps[:args.number_maps]:

        # Files to save clusterings
        json_file_path = os.path.join(get_results_path_for_method(args),
                                      semantic_map.semantic_map_id,
                                      "clustering.json")
        plot_file_path = os.path.join(get_results_path_for_method(args),
                                      semantic_map.semantic_map_id,
                                      "plot.png")

        print("#"*40)
        print(f"Processing {semantic_map.semantic_map_id}...")
        print("#"*40)

        # Assign geometric descriptors
        for semantic_map_object in tqdm(semantic_map.get_all_objects(),
                                        desc=f"Setting geometric descriptors {semantic_map.semantic_map_id}..."):

            # Geometric feature = bounding box
            semantic_map_object.geometric_descriptor = get_geometric_descriptor(
                semantic_map_object)

        if args.method == constants.METHOD_DEEPSEEK:

            place_classifier_prompt = PlaceSegmenterPrompt(
                semantic_map=semantic_map.get_json_representation())
            response = deepseek_llm.generate_json_retrying(prompt=place_classifier_prompt.get_prompt_text(),
                                                           params={
                                                               "max_length": 10000},
                                                           retries=10)

            # Check and create clustering
            mixed_clustering = Clustering([])
            for i, cluster_label in enumerate(response["places"]):
                # Create cluster
                cluster = Cluster(cluster_id=i,
                                  objects=[],
                                  description=cluster_label)
                # Fill with objects
                for object_id in response["places"][cluster_label]:
                    semantic_map_object = semantic_map.find_object(object_id)
                    print(semantic_map_object.object_id)
                    print(semantic_map_object.geometric_descriptor)
                    if semantic_map_object is not None:
                        cluster.append_object(semantic_map_object)
                # Append to clustering
                mixed_clustering.append_cluster(cluster)

        else:
            # Assign semantic descriptor
            for semantic_map_object in tqdm(semantic_map.get_all_objects(),
                                            desc=f"Generating features for {semantic_map.semantic_map_id}..."):
                # Use SemanticDescriptorEngine to generate semantic descriptor
                semantic_map_object.semantic_descriptor = semantic_descriptor_engine.get_semantic_descriptor_from_method(
                    args.method, semantic_map_object.get_most_probable_class()
                )

            # Convert features into numpy arrays
            # Shape: (num_objects, geometric_dim)
            print(list(map(lambda obj: obj.geometric_descriptor,
                           semantic_map.get_all_objects())))
            geometric_descriptor_matrix = np.array(
                list(map(lambda obj: obj.geometric_descriptor, semantic_map.get_all_objects())))
            print(
                f"[main] Geometric descriptor matrix shape: {geometric_descriptor_matrix.shape}")

            # Shape: (num_objects, semantic_dim)
            semantic_descriptor_matrix = np.array(
                list(map(lambda obj: obj.semantic_descriptor, semantic_map.get_all_objects())))
            print(
                f"[main] Semantic descriptor matrix shape: {semantic_descriptor_matrix.shape}")

            # Perform dimensionality reduction for semantic_features
            if args.method != constants.METHOD_GEOMETRIC and args.semantic_dimension is not None:
                reduced_semantic_descriptor_matrix = dim_reduction_engine.reduce(
                    semantic_descriptor_matrix,
                    args.semantic_dimension,
                    args.dimensionality_reductor
                )
            else:
                reduced_semantic_descriptor_matrix = semantic_descriptor_matrix

            # Normalize both descriptors separately
            normalized_geometric_descriptor_matrix = StandardScaler().fit_transform(
                geometric_descriptor_matrix)
            print(
                f"[main] Normalized geometric descriptor matrix shape: {normalized_geometric_descriptor_matrix.shape}")
            if args.method != constants.METHOD_GEOMETRIC:
                normalized_semantic_descriptor_matrix = StandardScaler().fit_transform(
                    reduced_semantic_descriptor_matrix)
                print(
                    f"[main] Normalized semantic descriptor matrix shape: {normalized_semantic_descriptor_matrix.shape}")
            else:
                normalized_semantic_descriptor_matrix = reduced_semantic_descriptor_matrix

            # Create mixed descriptor
            if args.method != constants.METHOD_GEOMETRIC:
                mixed_descriptor_matrix = np.hstack(
                    (normalized_geometric_descriptor_matrix, normalized_semantic_descriptor_matrix))
            else:
                mixed_descriptor_matrix = normalized_geometric_descriptor_matrix
            print(
                f"[main] Normalized mixed descriptor matrix shape: {mixed_descriptor_matrix.shape}")

            # Update object descriptors with normalized and reduced descriptors
            for i, object in enumerate(semantic_map.get_all_objects()):
                object.geometric_descriptor = list(
                    normalized_geometric_descriptor_matrix[i])
                object.semantic_descriptor = list(
                    normalized_semantic_descriptor_matrix[i])
                object.global_descriptor = list(mixed_descriptor_matrix[i])

            # Perform clustering
            clustering_engine = ClusteringEngine()
            mixed_clustering = clustering_engine.clusterize(
                semantic_map, args.clustering_algorithm, eps=args.eps, min_samples=args.min_samples, semantic_weight=args.semantic_weight, noise_objects_new_clusters=True)

            # Merge clusters
            if args.method in (constants.METHOD_BERT_POST, constants.METHOD_DEEPSEEK_SBERT_POST):
                mixed_clustering = clustering_engine.post_process_clustering(
                    semantic_map, mixed_clustering, args.merge_geometric_threshold, args.merge_semantic_threshold, args.split_semantic_threshold, json_file_path, plot_file_path)

        # Save clustering
        file_utils.create_directories_for_file(json_file_path)
        file_utils.create_directories_for_file(plot_file_path)
        mixed_clustering.save_to_json(json_file_path)
        mixed_clustering.visualize_2D(
            f"{semantic_map.semantic_map_id}\n s_d={args.method} eps={args.eps}, m_s={args.min_samples}, s_w={args.semantic_weight}, s_d={args.semantic_dimension}",
            semantic_map,
            geometric_threshold=args.merge_geometric_threshold,
            file_path=plot_file_path)

    print("[main] The main script finished successfully!")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Performs place categorization on a set of semantic map")

    parser.add_argument("-p", "--persist-log",
                        help="Redirect output to a log file instead of printing to the terminal.",
                        action="store_true")

    parser.add_argument("-n", "--number-maps",
                        help="Number of semantic map to which place categorization will be applied.",
                        type=int,
                        default=10)

    # SEMANTIC DESCRIPTOR parameters
    parser.add_argument("--method",
                        help="How to compute the semantic descriptor.",
                        choices=[constants.METHOD_GEOMETRIC,
                                 constants.METHOD_BERT,
                                 constants.METHOD_OPENAI,
                                 constants.METHOD_ROBERTA,
                                 constants.METHOD_DEEPSEEK_SBERT,
                                 constants.METHOD_DEEPSEEK_OPENAI,
                                 constants.METHOD_BERT_POST,
                                 constants.METHOD_DEEPSEEK_SBERT_POST,
                                 constants.METHOD_DEEPSEEK],
                        default=constants.METHOD_BERT)

    parser.add_argument("-w", "--semantic-weight",
                        help="Semantic weight in DBSCAN distance.",
                        type=float,
                        default=0.005)

    parser.add_argument("-d", "--semantic-dimension",
                        help="Dimensions to which reduce the semantic descriptor using PCA",
                        type=int,
                        default=None)

    parser.add_argument("-r", "--dimensionality_reductor",
                        help="Dimensionality reduction method to apply to the semantic descriptor.",
                        choices=[constants.DIM_REDUCTOR_PCA,
                                 constants.DIM_REDUCTOR_UMAP],
                        default=constants.DIM_REDUCTOR_PCA)

    # DBSCAN parameters
    parser.add_argument("-e", "--eps",
                        help="eps parameter in the DBSCAN algorithm",
                        type=float,
                        default=1.0)

    parser.add_argument("-m", "--min-samples",
                        help="min_samples parameter in the DBSCAN algorithm",
                        type=int,
                        default=2)

    # POST-PROCESSING parameters
    parser.add_argument("--merge-geometric-threshold",
                        help="Maximum distance between two clusters that could be merged",
                        type=float,
                        default=1.5)

    parser.add_argument("--merge-semantic-threshold",
                        help="Minimum semantic distance between two clusters that should be merged",
                        type=float,
                        default=0.99)

    parser.add_argument("--split-semantic-threshold",
                        help="Minimum semantic variance to split clusters",
                        type=float,
                        default=0.5)

    parser.add_argument("-c", "--clustering-algorithm",
                        help="Clustering algorithm to use.",
                        choices=[constants.CLUSTERING_ALGORITHM_DBSCAN,
                                 constants.CLUSTERING_ALGORITHM_HDBSCAN],
                        default=constants.CLUSTERING_ALGORITHM_DBSCAN)

    args = parser.parse_args()

    # Redirect output to a log file (args.persist_log)
    if args.persist_log:
        log_file_path = os.path.join(
            get_results_path_for_method(args), "log.txt")
        file_utils.create_directories_for_file(log_file_path)

        sys.stdout = open(log_file_path, "w")
        sys.stderr = sys.stdout

    main(args)
